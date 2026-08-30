package servicekit

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	rtmongo "quwoquan_service/internal/platform/mongodb"
	rthealth "quwoquan_service/runtime/health"
)

type bootstrapFixtureConfig struct {
	BaseConfig `yaml:",inline"`

	Greeting struct {
		Label string `yaml:"label" env:"GREETING_LABEL"`
	} `yaml:"greeting"`

	Redis struct {
		General RedisSceneConfig `yaml:"general" envPrefix:"REDIS_GENERAL"`
	} `yaml:"redis"`
}

func bootstrapTestEnvironment(t *testing.T, serviceName string) {
	t.Helper()
	authTestEnvironment(t)
	t.Setenv("APP_ENV", "alpha")
	t.Setenv(
		"IMAGE_VERSION",
		"sha256:2222222222222222222222222222222222222222222222222222222222222222",
	)
	t.Setenv("CONFIG_VERSION", "")
	t.Setenv("SERVICE_INSTANCE_ID", "test-instance-1")
	t.Setenv("RUNTIME_LOG_INGEST_URL", "")
	t.Setenv("RUNTIME_LOG_INGEST_TOKEN", "")
	t.Setenv("RUNTIME_LOG_SPOOL_DIR", "")
	t.Setenv("PLATFORM_OPS_BASE_URL", "")
	t.Setenv("VITE_PLATFORM_OPS_BASE_URL", "")

	root := t.TempDir()
	snapshot := strings.Join([]string{
		"config:",
		"  version: sha256:cfg-fixture",
		"service:",
		"  http:",
		"    addr: \":19081\"",
		"user_account_security_authority:",
		"  base_url: http://user.internal:18081",
		"  timeout_ms: 800",
		"greeting:",
		"  label: from-snapshot",
		// 不接真实 Redis 只能由 mode: memory 显式声明；省掉 redis 段会被装配期
		// 判否，而不是静默按进程内存实现装配。
		"redis:",
		"  general:",
		"    mode: memory",
		"",
	}, "\n")
	if err := os.WriteFile(
		filepath.Join(root, serviceName+".yaml"), []byte(snapshot), 0o644,
	); err != nil {
		t.Fatal(err)
	}
	t.Setenv("CONFIG_ROOT", root)
}

// memoryFixtureScenes 供「快照被换成不含 redis 段的最小形态」的用例使用：那些
// 用例测的是别的能力，但 scene 的 mode 仍必须显式声明，缺声明即判否。
func memoryFixtureScenes(*bootstrapFixtureConfig) map[string]RedisSceneConfig {
	return map[string]RedisSceneConfig{"general": {Mode: RedisModeMemory}}
}

func bootstrapFixtureSpec() BootstrapSpec[bootstrapFixtureConfig] {
	return BootstrapSpec[bootstrapFixtureConfig]{
		OperationDescriptors: authTestSpec().OperationDescriptors,
		AuthorityScopes:      []string{"user.account.security.read"},
		Assemble: func(asm *Assembly, cfg *bootstrapFixtureConfig) error {
			asm.Mux.HandleFunc("/greeting", func(http.ResponseWriter, *http.Request) {})
			return nil
		},
	}
}

func TestDefaultEnvPrefixDerivation(t *testing.T) {
	cases := map[string]string{
		"tag-service":         "TAG",
		"circle-service":      "CIRCLE",
		"product-ops-service": "PRODUCT_OPS",
		"realtime-gateway":    "REALTIME_GATEWAY",
	}
	for serviceName, expected := range cases {
		if actual := DefaultEnvPrefix(serviceName); actual != expected {
			t.Fatalf("DefaultEnvPrefix(%s)=%s, expected %s", serviceName, actual, expected)
		}
	}
}

func TestBootstrapFailsClosedOnIncompleteSpec(t *testing.T) {
	spec := bootstrapFixtureSpec()
	spec.Assemble = nil
	if _, err := Bootstrap("bootstrap-fixture", spec); err == nil ||
		!strings.Contains(err.Error(), "Assemble") {
		t.Fatalf("expected Assemble requirement, got %v", err)
	}

	spec = bootstrapFixtureSpec()
	spec.OperationDescriptors = nil
	if _, err := Bootstrap("bootstrap-fixture", spec); err == nil ||
		!strings.Contains(err.Error(), "operation descriptors") {
		t.Fatalf("expected descriptor requirement, got %v", err)
	}
}

func TestBootstrapRequiresEmbeddedBaseConfig(t *testing.T) {
	type detachedConfig struct {
		Anything string `yaml:"anything"`
	}
	bootstrapTestEnvironment(t, "bootstrap-fixture")
	_, err := Bootstrap("bootstrap-fixture", BootstrapSpec[detachedConfig]{
		OperationDescriptors: authTestSpec().OperationDescriptors,
		Assemble:             func(*Assembly, *detachedConfig) error { return nil },
	})
	if err == nil || !strings.Contains(err.Error(), "must embed servicekit.BaseConfig") {
		t.Fatalf("expected embedded BaseConfig requirement, got %v", err)
	}
}

func TestBootstrapAssemblesFullChain(t *testing.T) {
	bootstrapTestEnvironment(t, "bootstrap-fixture")

	var seen *bootstrapFixtureConfig
	spec := bootstrapFixtureSpec()
	wrapped := false
	spec.WrapHandler = func(handler http.Handler) http.Handler {
		wrapped = true
		return handler
	}
	innerAssemble := spec.Assemble
	spec.Assemble = func(asm *Assembly, cfg *bootstrapFixtureConfig) error {
		seen = cfg
		asm.Workers.Add(func(context.Context) {})
		return innerAssemble(asm, cfg)
	}

	assembly, module, err := bootstrapAssembly("bootstrap-fixture", spec)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	t.Cleanup(func() { _ = assembly.Cleanups.Close(context.Background()) })

	if seen == nil || seen.Greeting.Label != "from-snapshot" {
		t.Fatalf("domain assembly must observe the loaded config, got %+v", seen)
	}
	if module.ConfigDigest() != "sha256:cfg-fixture" {
		t.Fatalf("expected snapshot version as config digest, got %q", module.ConfigDigest())
	}
	if module.server.Addr != ":19081" {
		t.Fatalf("expected snapshot listen addr, got %q", module.server.Addr)
	}
	if !wrapped {
		t.Fatal("WrapHandler hook must be applied")
	}
	// 声明即装配：config struct 声明了 RedisSceneConfig 字段（空地址 →
	// memory 模式），无需任何回调。
	if assembly.RedisRouter == nil || assembly.RedisSceneModes["general"] != "memory" {
		t.Fatalf(
			"expected auto-discovered memory-mode redis scene, got %v",
			assembly.RedisSceneModes,
		)
	}
	if len(assembly.Workers.starts) != 1 {
		t.Fatalf("expected exactly the domain worker, got %d", len(assembly.Workers.starts))
	}

	checks := assembly.Health.Check(context.Background()).Checks
	for _, required := range []string{"account_security_authority", "redis"} {
		if _, registered := checks[required]; !registered {
			t.Fatalf("expected %s health registration, got %v", required, checks)
		}
	}

	// 探针端点由骨架统一挂载：readinessProbe 指 /readyz、liveness 指 /healthz。
	for _, probePath := range []string{"/healthz", "/readyz", "/metrics"} {
		recorder := httptest.NewRecorder()
		module.server.Handler.ServeHTTP(
			recorder, httptest.NewRequest(http.MethodGet, probePath, nil),
		)
		if recorder.Code == http.StatusNotFound {
			t.Fatalf("probe endpoint %s must be mounted by the skeleton", probePath)
		}
	}
}

// TestBootstrapOmitsAccountSecurityReadinessWhenAbsenceIsDeclared 锁定控制面
// 服务的就绪面：声明账号安全 authority 缺席后，骨架不再把它并入 /readyz。
// 登记一个必然失败的检查会让「本服务无此依赖」持续报成依赖故障。
func TestBootstrapOmitsAccountSecurityReadinessWhenAbsenceIsDeclared(t *testing.T) {
	bootstrapTestEnvironment(t, "bootstrap-fixture")
	root := os.Getenv("CONFIG_ROOT")
	snapshot := strings.Join([]string{
		"config:",
		"  version: sha256:cfg-fixture",
		"service:",
		"  http:",
		"    addr: \":19081\"",
		"",
	}, "\n")
	if err := os.WriteFile(
		filepath.Join(root, "bootstrap-fixture.yaml"), []byte(snapshot), 0o644,
	); err != nil {
		t.Fatal(err)
	}

	spec := bootstrapFixtureSpec()
	spec.AuthorityScopes = nil
	spec.SkipAccountSecurityAuthority = true
	spec.RedisScenes = memoryFixtureScenes
	assembly, _, err := bootstrapAssembly("bootstrap-fixture", spec)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	t.Cleanup(func() { _ = assembly.Cleanups.Close(context.Background()) })

	checks := assembly.Health.Check(context.Background()).Checks
	if _, registered := checks["account_security_authority"]; registered {
		t.Fatalf("declared absence must not register the readiness check, got %v", checks)
	}
	if assembly.Auth.AccountSecurityAuthority != nil {
		t.Fatal("declared absence must not assemble an authority client")
	}
}

func TestBootstrapDerivedEnvPrefixReachesModule(t *testing.T) {
	bootstrapTestEnvironment(t, "bootstrap-fixture")
	// 前缀由服务名派生：bootstrap-fixture → BOOTSTRAP_FIXTURE。
	t.Setenv("BOOTSTRAP_FIXTURE_SERVICE_ADDR", ":19099")
	t.Setenv("BOOTSTRAP_FIXTURE_GREETING_LABEL", "from-env")

	var seen *bootstrapFixtureConfig
	spec := bootstrapFixtureSpec()
	innerAssemble := spec.Assemble
	spec.Assemble = func(asm *Assembly, cfg *bootstrapFixtureConfig) error {
		seen = cfg
		return innerAssemble(asm, cfg)
	}
	assembly, module, err := bootstrapAssembly("bootstrap-fixture", spec)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	t.Cleanup(func() { _ = assembly.Cleanups.Close(context.Background()) })

	if module.server.Addr != ":19099" {
		t.Fatalf("derived-prefix env override must reach the listener, got %q", module.server.Addr)
	}
	if seen.Greeting.Label != "from-env" {
		t.Fatalf("derived-prefix env override must reach domain config, got %q", seen.Greeting.Label)
	}
}

func TestBootstrapExplicitEnvPrefixOverridesDerivation(t *testing.T) {
	bootstrapTestEnvironment(t, "bootstrap-fixture")
	t.Setenv("LEGACY_SERVICE_ADDR", ":19100")

	spec := bootstrapFixtureSpec()
	spec.EnvPrefix = "LEGACY"
	assembly, module, err := bootstrapAssembly("bootstrap-fixture", spec)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	t.Cleanup(func() { _ = assembly.Cleanups.Close(context.Background()) })
	if module.server.Addr != ":19100" {
		t.Fatalf("explicit EnvPrefix must win over derivation, got %q", module.server.Addr)
	}
}

// TestBootstrapAutoAssemblesDeclaredMongo 锁定「声明即装配」：config struct
// 声明 MongoConfig 字段后，Bootstrap 自动连接并暴露 Assembly.MongoDB，健康
// 检查与清理注册由构件承担。
func TestBootstrapAutoAssemblesDeclaredMongo(t *testing.T) {
	type mongoFixtureConfig struct {
		BaseConfig `yaml:",inline"`
		Mongo      MongoConfig `yaml:"mongo"`
	}

	bootstrapTestEnvironment(t, "bootstrap-fixture")
	root := os.Getenv("CONFIG_ROOT")
	snapshot := strings.Join([]string{
		"config:",
		"  version: sha256:cfg-fixture",
		"service:",
		"  http:",
		"    addr: \":19081\"",
		"user_account_security_authority:",
		"  base_url: http://user.internal:18081",
		"  timeout_ms: 800",
		"mongo:",
		"  uri: mongodb://db.internal:27017",
		"  database: quwoquan_fixture",
		"",
	}, "\n")
	if err := os.WriteFile(
		filepath.Join(root, "bootstrap-fixture.yaml"), []byte(snapshot), 0o644,
	); err != nil {
		t.Fatal(err)
	}

	double := &mongoClientDouble{}
	original := defaultMongoConnect
	defaultMongoConnect = func(_ context.Context, cfg rtmongo.ConnectConfig) (rtmongo.Handle, error) {
		if cfg.URI != "mongodb://db.internal:27017" {
			t.Fatalf("declared uri must reach the connector, got %q", cfg.URI)
		}
		return double, nil
	}
	t.Cleanup(func() { defaultMongoConnect = original })

	assembled := false
	assembly, _, err := bootstrapAssembly("bootstrap-fixture", BootstrapSpec[mongoFixtureConfig]{
		OperationDescriptors: authTestSpec().OperationDescriptors,
		AuthorityScopes:      []string{"user.account.security.read"},
		Assemble: func(asm *Assembly, cfg *mongoFixtureConfig) error {
			assembled = true
			return nil
		},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	t.Cleanup(func() { _ = assembly.Cleanups.Close(context.Background()) })

	if !assembled {
		t.Fatal("domain assembly must run")
	}
	checks := assembly.Health.Check(context.Background()).Checks
	if _, registered := checks["mongodb"]; !registered {
		t.Fatalf("declared mongo must auto-register its health check, got %v", checks)
	}
}

// TestBootstrapConfigDigestFallsBackToDescriptorSHA 锁定 digest 推导链末级：
// 快照无 config.version 且无 CONFIG_VERSION 时取 descriptors 携带的
// ContractGraphSHA256。
func TestBootstrapConfigDigestFallsBackToDescriptorSHA(t *testing.T) {
	bootstrapTestEnvironment(t, "bootstrap-fixture")
	root := os.Getenv("CONFIG_ROOT")
	snapshot := strings.Join([]string{
		"service:",
		"  http:",
		"    addr: \":19081\"",
		"user_account_security_authority:",
		"  base_url: http://user.internal:18081",
		"  timeout_ms: 800",
		"",
	}, "\n")
	if err := os.WriteFile(
		filepath.Join(root, "bootstrap-fixture.yaml"), []byte(snapshot), 0o644,
	); err != nil {
		t.Fatal(err)
	}

	spec := bootstrapFixtureSpec()
	spec.RedisScenes = memoryFixtureScenes
	assembly, module, err := bootstrapAssembly("bootstrap-fixture", spec)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	t.Cleanup(func() { _ = assembly.Cleanups.Close(context.Background()) })
	expected := authTestSpec().OperationDescriptors[0].ContractGraphSHA256
	if module.ConfigDigest() != expected {
		t.Fatalf("expected descriptor SHA fallback, got %q", module.ConfigDigest())
	}
}

func TestDiscoverInfrastructureFailsClosedOnAmbiguity(t *testing.T) {
	type doubleMongo struct {
		Primary   MongoConfig `yaml:"primary"`
		Secondary MongoConfig `yaml:"secondary"`
	}
	if _, err := discoverInfrastructure(&doubleMongo{}); err == nil ||
		!strings.Contains(err.Error(), "multiple MongoConfig") {
		t.Fatalf("expected multiple-mongo rejection, got %v", err)
	}

	type untaggedScene struct {
		Scene RedisSceneConfig
	}
	if _, err := discoverInfrastructure(&untaggedScene{}); err == nil ||
		!strings.Contains(err.Error(), "yaml tag") {
		t.Fatalf("expected untagged scene rejection, got %v", err)
	}

	type duplicateScenes struct {
		A struct {
			General RedisSceneConfig `yaml:"general"`
		} `yaml:"a"`
		B struct {
			General RedisSceneConfig `yaml:"general"`
		} `yaml:"b"`
	}
	if _, err := discoverInfrastructure(&duplicateScenes{}); err == nil ||
		!strings.Contains(err.Error(), "duplicate Redis scene") {
		t.Fatalf("expected duplicate scene rejection, got %v", err)
	}

	type doublePostgres struct {
		Primary  PostgresConfig `yaml:"primary"`
		Replica  PostgresConfig `yaml:"replica"`
		Unstated int
	}
	if _, err := discoverInfrastructure(&doublePostgres{}); err == nil ||
		!strings.Contains(err.Error(), "multiple PostgresConfig") {
		t.Fatalf("expected multiple-postgres rejection, got %v", err)
	}
}

// TestDiscoverInfrastructureFindsPostgresDeclaration 锁定「声明即装配」对
// Postgres 生效：config struct 内嵌 PostgresConfig 即被发现，池参数原样透传。
func TestDiscoverInfrastructureFindsPostgresDeclaration(t *testing.T) {
	type withPostgres struct {
		Storage struct {
			Postgres PostgresConfig `yaml:"postgres"`
		} `yaml:"storage"`
	}
	cfg := &withPostgres{}
	cfg.Storage.Postgres.DSN = "postgres://user:pass@db:5432/app"
	cfg.Storage.Postgres.MaxOpenConns = 8

	discovered, err := discoverInfrastructure(cfg)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if discovered.postgres == nil {
		t.Fatal("declared PostgresConfig must be discovered")
	}
	if discovered.postgres.DSN != cfg.Storage.Postgres.DSN ||
		discovered.postgres.MaxOpenConns != 8 {
		t.Fatalf("declared postgres config must pass through, got %+v", *discovered.postgres)
	}
}

// TestPostgresAssemblyRejectsMissingDSN 锁定 fail-closed：DSN 缺失即失败，
// 不允许回落到任何内置默认连接串。
func TestPostgresAssemblyRejectsMissingDSN(t *testing.T) {
	assembly := &Assembly{
		Identity: Identity{ServiceName: "postgres-fixture"},
		Health:   rthealth.NewChecker(),
		Cleanups: &CleanupStack{},
		Context:  context.Background(),
	}
	if _, err := assembly.Postgres(PostgresConfig{DSN: "   "}); err == nil ||
		!strings.Contains(err.Error(), "postgres.dsn is required") {
		t.Fatalf("expected missing dsn rejection, got %v", err)
	}
	if _, err := assembly.Postgres(PostgresConfig{DSN: "not-a-dsn://%zz"}); err == nil ||
		!strings.Contains(err.Error(), "postgres.dsn invalid") {
		t.Fatalf("expected invalid dsn rejection, got %v", err)
	}
}

// TestBootstrapRegistersConfigSyncContract 锁定 DEC-028 的契约行为：控制面
// 地址在场时，调用 Bootstrap 必然注册 config sync worker 与 config_sync 健康
// 检查，config ACK gate 认 servicekit.Bootstrap( 字面量的语义依赖本断言。
func TestBootstrapRegistersConfigSyncContract(t *testing.T) {
	bootstrapTestEnvironment(t, "bootstrap-fixture")
	t.Setenv("PLATFORM_OPS_BASE_URL", "http://platform-ops.internal:18099")

	assembly, _, err := bootstrapAssembly("bootstrap-fixture", bootstrapFixtureSpec())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	t.Cleanup(func() { _ = assembly.Cleanups.Close(context.Background()) })

	checks := assembly.Health.Check(context.Background()).Checks
	if _, registered := checks["config_sync"]; !registered {
		t.Fatalf("Bootstrap must register the config_sync health check, got %v", checks)
	}
	if len(assembly.Workers.starts) != 1 {
		t.Fatalf("Bootstrap must register the config sync worker, got %d", len(assembly.Workers.starts))
	}
}

// TestBootstrapNormalizesObservedEndpointToContractTemplate 锁定观测面的
// endpoint 维度取 contract 的 operation path template：路径里的 id 不进标签，
// 否则 http_server_* series 的基数随实体数量增长，且与 ContractGraph 声明的
// telemetry 维度不同源。
func TestBootstrapNormalizesObservedEndpointToContractTemplate(t *testing.T) {
	bootstrapTestEnvironment(t, "bootstrap-fixture")

	assembly, module, err := bootstrapAssembly("bootstrap-fixture", bootstrapFixtureSpec())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	t.Cleanup(func() { _ = assembly.Cleanups.Close(context.Background()) })

	if err := module.OpenAdmission(context.Background()); err != nil {
		t.Fatalf("open admission: %v", err)
	}
	module.server.Handler.ServeHTTP(
		httptest.NewRecorder(),
		httptest.NewRequest(http.MethodGet, "/circles/circle-9c3f", nil),
	)

	scrape := httptest.NewRecorder()
	module.server.Handler.ServeHTTP(
		scrape, httptest.NewRequest(http.MethodGet, "/metrics", nil),
	)
	exposition := scrape.Body.String()
	if !strings.Contains(exposition, `/circles/{circleId}`) {
		t.Fatal("observed endpoint label must be the contract path template")
	}
	if strings.Contains(exposition, "circle-9c3f") {
		t.Fatal("concrete resource ids must not reach the endpoint label")
	}
}
