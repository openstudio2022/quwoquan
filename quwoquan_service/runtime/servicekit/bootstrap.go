package servicekit

import (
	"context"
	"fmt"
	"net/http"
	"reflect"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtredis "quwoquan_service/runtime/redis"
)

// BaseConfig 是声明式 Bootstrap 要求内嵌进服务 config struct 的通用段：
// 配置快照版本、HTTP 监听地址与账号安全 authority 标准段。yaml.v3 对匿名
// 内嵌默认 inline 展开，服务侧无需额外声明。
type BaseConfig struct {
	Config struct {
		Version string `yaml:"version"`
	} `yaml:"config"`

	// Environment 是 canonical 应用环境，不出现在配置快照里：它由骨架从进程
	// 身份写入，供按环境分档的领域校验直接读取，避免各服务自建第二来源。
	Environment string `yaml:"-"`

	// ConfigPath 是本次生效的配置快照文件路径，同样由骨架写入、不出现在快照
	// 里。需要按快照来源分档校验的领域钩子（如「渲染快照缺失时拒绝启动」）
	// 读它，而不是各自重算一遍解析规则。
	ConfigPath string `yaml:"-"`

	Service struct {
		HTTP struct {
			Addr string `yaml:"addr" env:"SERVICE_ADDR" required:"true"`
		} `yaml:"http"`
	} `yaml:"service"`

	UserAccountSecurityAuthority struct {
		BaseURL   string `yaml:"base_url" env:"USER_ACCOUNT_SECURITY_AUTHORITY_BASE_URL"`
		TimeoutMs int    `yaml:"timeout_ms"`
	} `yaml:"user_account_security_authority"`
}

// BootstrapSpec 是声明式装配的全部服务侧输入（DEC-028）。类型参数 T 是服务
// 的 config struct，必须匿名内嵌 BaseConfig。
type BootstrapSpec[T any] struct {
	// OperationDescriptors 由服务从自己的 generated 包构造
	// （operationsecurity.ForDomain）；servicekit 不 import generated。
	// ConfigDigest 的末级回退也取自 descriptors 携带的 ContractGraphSHA256。
	OperationDescriptors []rtauth.OperationSecurityDescriptor
	// AuthorityScopes 是该服务对账号安全 authority 的最小服务间授权范围。
	AuthorityScopes []string
	// SkipDeviceTicketAuth 声明本服务不提供设备票据认证能力，透传给 auth 栈。
	SkipDeviceTicketAuth bool
	// SkipAccountSecurityAuthority 声明本服务的入站面不接受终端用户账号
	// principal（控制面服务只认运营台 OIDC 与机器凭据），透传给 auth 栈：
	// 不装配 authority 客户端、不登记其就绪检查，需要账号安全裁决的 principal
	// 由中间件 fail-closed 拒绝。它与 AuthorityScopes 互斥。
	SkipAccountSecurityAuthority bool
	// SelfHostedAccountSecurityAuthority 声明本服务就是账号安全 authority 的
	// 提供方（user-service），透传给 auth 栈。裁决 gate 必须在 Assemble 里经
	// Assembly.Auth.ProvideInProcessAccountSecurityGate 交出，由骨架挂在
	// operation guard 内侧；缺提供即启动失败。
	SelfHostedAccountSecurityAuthority bool
	// OperatorOIDCEnvPrefix 声明本服务承载运营台身份，透传给 auth 栈按该
	// 前缀装配 OIDC verifier（如 product-ops 的 OPS_OIDC）。
	OperatorOIDCEnvPrefix string
	// ObservabilityKVFilter 决定进程 trace 的 input/output KV 元数据脱敏策略；
	// nil 表示原样记录。处理凭据、令牌一类敏感载荷的服务必须显式传入。
	ObservabilityKVFilter *robs.KVMetadataFilter
	// EnvPrefix 覆盖默认派生的 env 键前缀（服务名去 -service 后缀 token 化，
	// 如 tag-service → TAG）；仅历史键名不合派生规则时使用。
	EnvPrefix string
	// RetiredEnvKeys 声明已退役的环境变量键。任一键在进程环境中出现即
	// fail-closed，落实「契约单轨、禁止 compat/warn-only 逃逸」。
	RetiredEnvKeys []string
	// SnapshotGuard 对配置快照原文做形状校验，用于拒收已退役配置段。
	// 在反序列化之后、env 覆盖之前执行。
	SnapshotGuard func(raw []byte) error
	// ValidateConfig 是领域配置校验钩子，在 required 校验之后、任何观测栈与
	// 基础设施连接之前执行，保证非法配置不产生外部副作用。
	ValidateConfig func(cfg *T) error
	// RedisScenes 覆盖「声明即装配」的 scene 自动发现，用于一份 scene 配置
	// 要装配成多个 codegen scene 名的服务（如 general/rec/realtime 共用）。
	// nil 时按 config struct 的 RedisSceneConfig 字段自动发现。
	RedisScenes func(cfg *T) map[string]RedisSceneConfig
	// WrapHandler 承载真正特殊的服务级中间件；nil 表示无。它在认证中间件
	// **内侧**（即已解析出 principal 之后）生效。跨域策略走 CORS 声明位。
	WrapHandler func(handler http.Handler) http.Handler
	// WrapOutsideAuth 承载必须在认证中间件**外侧**生效的中间件；nil 表示无。
	// 认证中间件会把原始凭据头换成已解析的 principal 上下文，因此需要看到
	// 原始入站报文的关注点（网关的凭据中继）只能挂在它外侧。这个位置绕不过
	// 认证——认证仍在它内侧执行，它只是先于认证观察请求。
	WrapOutsideAuth func(handler http.Handler) http.Handler
	// OperationGuard 覆盖默认的 public boundary operation guard，用于按
	// runtime boundary 判定的服务（rtauth.EnforceRuntimeOperationContract）。
	// 两种 boundary 都是 runtime/auth 的合法策略，选择权归服务。
	// 回调收到进程身份并允许返回错误：按环境分档的 boundary（如
	// rtauth.OperationAuthorizationForRuntime）需要 env，且构造可失败，
	// 失败必须阻止启动而不是退化成无 guard。
	OperationGuard func(identity Identity) (func(handler http.Handler) http.Handler, error)
	// ConfigSync 透传 config sync 注册选项；注册本身由 Bootstrap 契约内置。
	ConfigSync ConfigSyncOptions
	// PrepareMigration 可选，透传 servicehost PrepareMigration 相位。
	PrepareMigration func(ctx context.Context) error
	// ReadinessTimeout 透传 ModuleSpec；零值取默认。
	ReadinessTimeout time.Duration
	// CORS 声明本服务的浏览器跨域策略；nil 表示**不挂载** CORS 中间件，
	// OPTIONS 按普通请求进入路由与 operation guard，由 ContractGraph 裁决。
	//
	// 默认不挂载，因为 rthttp.WithCORS 对 OPTIONS 无条件短路返回 204——那是
	// 一个不过观测、不过 operation guard、不过共享准入、也不计量的未认证请求
	// 面。它是入站面策略而非通用样板：只有真正接受浏览器跨域直连的服务才该
	// 开它，其余服务开了就等于凭空多一个对外可探测面。
	CORS *rthttp.CORSOptions
	// PreAdmissionPaths 声明在 OpenAdmission 之前即放行的内部端点。仅用于
	// 打破 service-core 单进程内的启动循环（同进程另一模块的就绪检查要调用
	// 本模块的内部端点）。判据窄化到精确 `/internal/` 路径，见
	// normalizePreAdmissionPaths。
	PreAdmissionPaths []string
	// HijacksConnections 声明本服务会把连接从 net/http 接管出去
	// （WebSocket 升级、长轮询）。此时不能设置 WriteTimeout：Go 不会为已
	// hijack 的连接重置写截止时间，请求级上限由 operation guard 施加的
	// reliability.timeout_ms 承担。
	HijacksConnections bool
	// Assemble 是领域装配回调：store/facade/worker 构造、路由注册、
	// 领域健康检查。必填。
	Assemble func(asm *Assembly, cfg *T) error
}

// Assembly 是领域装配回调可见的装配面。基础设施构件按「声明即装配」自动
// 发现：config struct 声明 MongoConfig / PostgresConfig / RedisSceneConfig
// 字段即自动装配。
type Assembly struct {
	Identity      Identity
	Health        *rthealth.Checker
	Workers       *WorkerRegistry
	Cleanups      *CleanupStack
	Auth          *AuthStack
	Observability *ObservabilityStack
	// MongoDB 在 config struct 声明了 MongoConfig 字段后自动连接可用。
	MongoDB MongoDatabase
	// PostgresPool 在 config struct 声明了 PostgresConfig 字段后自动连接可用。
	PostgresPool PostgresPool
	// RedisRouter 与 RedisSceneModes 在 config struct 声明了 RedisSceneConfig
	// 字段后自动装配。
	RedisRouter     *rtredis.Router
	RedisSceneModes map[string]string
	// Mux 是领域路由注册点；operation guard、healthz、metrics 由骨架挂接。
	Mux *http.ServeMux
	// Context 是装配期上下文，供 EnsureIndexes 等一次性初始化使用。
	Context context.Context

	mongoConnect mongoConnectFunc
	unguardedMux *http.ServeMux
}

// Unguarded 返回不经过 operation guard 的路由注册点，懒创建。仅用于自行在
// handler 内执行同一 operation contract 的入站面（如 WebSocket 升级）。
// 未调用本方法的服务，全部领域路由都在 guard 之下。
func (assembly *Assembly) Unguarded() *http.ServeMux {
	if assembly.unguardedMux == nil {
		assembly.unguardedMux = http.NewServeMux()
	}
	return assembly.unguardedMux
}

// livenessHandler 只回答进程存活，不触达任何依赖。
func livenessHandler(writer http.ResponseWriter, _ *http.Request) {
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(http.StatusOK)
	_, _ = writer.Write([]byte(`{"status":"ok"}`))
}

// unguardedFirstHandler 优先把请求交给 unguarded 路由表；未匹配时回落到
// guard 之后的领域路由。
func unguardedFirstHandler(unguarded *http.ServeMux, guarded http.Handler) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if _, pattern := unguarded.Handler(request); pattern != "" {
			unguarded.ServeHTTP(writer, request)
			return
		}
		guarded.ServeHTTP(writer, request)
	})
}

// DefaultEnvPrefix 派生服务的默认 env 键前缀：去 -service 后缀后 token 化。
// tag-service → TAG、circle-service → CIRCLE、realtime-gateway → REALTIME_GATEWAY。
func DefaultEnvPrefix(serviceName string) string {
	trimmed := strings.TrimSuffix(strings.TrimSpace(serviceName), "-service")
	return environmentToken(trimmed)
}

// Bootstrap 按声明式规范装配一个通用 servicehost 模块（DEC-028）：
// 身份解析 → 快照加载 → env 覆盖 → required 校验 → 身份校验 → 观测栈 →
// auth 栈 → 基础设施自动装配 → 领域装配 → HTTP 三件套 → CORS/中间件 →
// config sync → ModuleSpec。config sync 注册是本骨架的契约行为，由同包
// 白盒测试锁定。
func Bootstrap[T any](serviceName string, spec BootstrapSpec[T]) (*Module, error) {
	_, module, err := bootstrapAssembly(serviceName, spec)
	return module, err
}

func bootstrapAssembly[T any](
	serviceName string,
	spec BootstrapSpec[T],
) (_ *Assembly, _ *Module, resultErr error) {
	if spec.Assemble == nil {
		return nil, nil, fmt.Errorf("%s bootstrap requires an Assemble callback", serviceName)
	}
	if len(spec.OperationDescriptors) == 0 {
		return nil, nil, fmt.Errorf(
			"%s bootstrap requires generated operation descriptors", serviceName,
		)
	}
	envPrefix := strings.TrimSpace(spec.EnvPrefix)
	if envPrefix == "" {
		envPrefix = DefaultEnvPrefix(serviceName)
	}
	if envPrefix == "" {
		return nil, nil, fmt.Errorf("%s bootstrap could not derive an env prefix", serviceName)
	}

	cleanups := &CleanupStack{}
	initialized := false
	defer func() {
		if initialized {
			return
		}
		cleanupCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = cleanups.Close(cleanupCtx)
	}()

	identity, err := ResolveIdentity(serviceName)
	if err != nil {
		return nil, nil, fmt.Errorf("%s runtime identity invalid: %w", serviceName, err)
	}

	if err := RejectRetiredEnvKeys(spec.RetiredEnvKeys); err != nil {
		return nil, nil, fmt.Errorf("%s retired env key rejected: %w", serviceName, err)
	}

	cfg := new(T)
	raw, err := LoadYAMLConfigRaw(identity, cfg)
	if err != nil {
		return nil, nil, fmt.Errorf("%s config load failed: %w", serviceName, err)
	}
	if spec.SnapshotGuard != nil {
		if err := spec.SnapshotGuard(raw); err != nil {
			return nil, nil, fmt.Errorf("%s config snapshot rejected: %w", serviceName, err)
		}
	}
	base, err := extractBaseConfig(cfg)
	if err != nil {
		return nil, nil, fmt.Errorf("%s bootstrap config: %w", serviceName, err)
	}
	base.Environment = identity.AppEnv
	configPath, err := ConfigPathFor(identity)
	if err != nil {
		return nil, nil, fmt.Errorf("%s config path unresolved: %w", serviceName, err)
	}
	base.ConfigPath = configPath
	if err := ApplyEnvOverrides(envPrefix, cfg); err != nil {
		return nil, nil, fmt.Errorf("%s env override failed: %w", serviceName, err)
	}
	if err := ValidateRequired(cfg); err != nil {
		return nil, nil, fmt.Errorf("%s config validation failed: %w", serviceName, err)
	}
	if spec.ValidateConfig != nil {
		if err := spec.ValidateConfig(cfg); err != nil {
			return nil, nil, fmt.Errorf("%s config validation failed: %w", serviceName, err)
		}
	}
	if err := ValidateConfigIdentity(base.Config.Version, identity); err != nil {
		return nil, nil, fmt.Errorf("%s config identity failed: %w", serviceName, err)
	}

	observability, err := NewObservabilityStack(identity, spec.ObservabilityKVFilter)
	if err != nil {
		return nil, nil, err
	}
	cleanups.Add(observability.CleanupFunc())

	authStack, err := NewAuthStack(identity, AuthStackSpec{
		OperationDescriptors: spec.OperationDescriptors,
		AccountSecurityAuthority: AccountSecurityAuthoritySpec{
			BaseURL:   base.UserAccountSecurityAuthority.BaseURL,
			TimeoutMs: base.UserAccountSecurityAuthority.TimeoutMs,
			Scopes:    spec.AuthorityScopes,
		},
		SkipDeviceTicketAuth:               spec.SkipDeviceTicketAuth,
		SkipAccountSecurityAuthority:       spec.SkipAccountSecurityAuthority,
		SelfHostedAccountSecurityAuthority: spec.SelfHostedAccountSecurityAuthority,
		OperatorOIDCEnvPrefix:              spec.OperatorOIDCEnvPrefix,
	})
	if err != nil {
		return nil, nil, err
	}

	health := rthealth.NewChecker()
	// 检查名沿用存量多数派的下划线形态：它是 healthz 的可观测键，
	// 多个服务的 security wiring 测试以此名取证。声明缺席的服务没有这个
	// 依赖，登记一个必然失败的检查会把「无依赖」误报成「依赖故障」。
	if authStack.AccountSecurityAuthority != nil {
		health.Register("account_security_authority", func(hctx context.Context) error {
			return authStack.AccountSecurityAuthority.CheckAccountSecurityAuthority(hctx)
		})
	}

	workers := &WorkerRegistry{}
	assembly := &Assembly{
		Identity:      identity,
		Health:        health,
		Workers:       workers,
		Cleanups:      cleanups,
		Auth:          authStack,
		Observability: observability,
		Mux:           http.NewServeMux(),
		Context:       context.Background(),
		mongoConnect:  defaultMongoConnect,
	}

	infrastructure, err := discoverInfrastructure(cfg)
	if err != nil {
		return nil, nil, fmt.Errorf("%s infrastructure discovery failed: %w", serviceName, err)
	}
	redisScenes := infrastructure.redisScenes
	if spec.RedisScenes != nil {
		redisScenes = spec.RedisScenes(cfg)
	}
	if len(redisScenes) > 0 {
		router, sceneModes, err := NewRedisRouter(redisScenes)
		if err != nil {
			return nil, nil, fmt.Errorf("%s redis router build failed: %w", serviceName, err)
		}
		cleanups.Add(func(context.Context) error { return router.Close() })
		health.Register("redis", router.PingAll)
		assembly.RedisRouter = router
		assembly.RedisSceneModes = sceneModes
	}
	if infrastructure.mongo != nil {
		database, err := assembly.Mongo(*infrastructure.mongo)
		if err != nil {
			return nil, nil, err
		}
		assembly.MongoDB = database
	}
	if infrastructure.postgres != nil {
		pool, err := assembly.Postgres(*infrastructure.postgres)
		if err != nil {
			return nil, nil, err
		}
		assembly.PostgresPool = pool
	}

	if err := spec.Assemble(assembly, cfg); err != nil {
		return nil, nil, fmt.Errorf("%s domain assembly failed: %w", serviceName, err)
	}
	if err := authStack.requireAccountSecurityDecisionPoint(); err != nil {
		return nil, nil, err
	}

	outerMux := http.NewServeMux()
	// liveness 与 readiness 语义分离：/healthz 只回答「进程还在跑」，
	// /readyz 回答「依赖是否就绪」。把依赖检查放进 liveness 会让下游抖动
	// 触发容器重启，对长连接服务尤其有害；deploy 的 liveness/startup 指向
	// /healthz，readiness 指向 /readyz。
	outerMux.HandleFunc("/healthz", livenessHandler)
	outerMux.HandleFunc("/readyz", health.Handler())
	outerMux.Handle("/metrics", rtmetrics.Handler())
	guard := authStack.GuardOperations
	if spec.OperationGuard != nil {
		selected, err := spec.OperationGuard(identity)
		if err != nil {
			return nil, nil, fmt.Errorf("%s operation guard invalid: %w", serviceName, err)
		}
		if selected == nil {
			return nil, nil, fmt.Errorf("%s operation guard returned no middleware", serviceName)
		}
		guard = selected
	}
	// 自托管 authority 的领域裁决 gate 挂在 operation guard 内侧：guard 先写入
	// operation 上下文，gate 才能按 canonical operation 表达豁免。挂到外侧会让
	// 这类豁免静默失效。
	var domainRoot http.Handler = assembly.Mux
	if gate := authStack.inProcessAccountSecurityGate; gate != nil {
		domainRoot = gate(domainRoot)
	}
	domainHandler := guard(domainRoot)
	// Unguarded 面承载不能过 operation guard 的入站路由（如 WebSocket 升级：
	// 它在 handler 内消费一次性 ticket 注入可信 principal 后，自行执行同一
	// runtime operation contract）。它仍然过认证中间件与观测栈。
	if assembly.unguardedMux != nil {
		domainHandler = unguardedFirstHandler(assembly.unguardedMux, domainHandler)
	}
	outerMux.Handle("/", domainHandler)

	// endpoint 维度统一取 contract 的 operation path template：观测面与
	// ContractGraph 同源，且不会因 path 里的 id 造成标签基数爆炸。
	handler := observability.WrapHTTPHandler(
		outerMux,
		identity,
		rtauth.NewOperationPathTemplateResolver(spec.OperationDescriptors),
	)
	if spec.CORS != nil {
		handler = rthttp.WithCORS(handler, *spec.CORS)
	}
	if spec.WrapHandler != nil {
		handler = spec.WrapHandler(handler)
	}
	handler = authStack.WrapHTTPHandler(handler)
	// 认证之外的最后一层：它先于认证观察请求，因此能看到原始凭据头。
	if spec.WrapOutsideAuth != nil {
		handler = spec.WrapOutsideAuth(handler)
	}

	if _, err := RegisterConfigSync(workers, health, identity, spec.ConfigSync); err != nil {
		return nil, nil, err
	}

	configDigest := identity.ConfigVersion
	if configDigest == "" {
		configDigest = base.Config.Version
	}
	if configDigest == "" {
		configDigest = spec.OperationDescriptors[0].ContractGraphSHA256
	}
	writeTimeout := authStack.Timeouts.Write
	if spec.HijacksConnections {
		writeTimeout = 0
	}
	module, err := NewModule(ModuleSpec{
		Identity:     identity,
		ListenAddr:   base.Service.HTTP.Addr,
		ConfigDigest: configDigest,
		Handler:      handler,
		Timeouts: HTTPServerTimeouts{
			ReadHeader: authStack.Timeouts.ReadHeader,
			Write:      writeTimeout,
			Idle:       authStack.Timeouts.Idle,
		},
		Health:            health,
		Workers:           workers,
		Cleanups:          cleanups,
		PrepareMigration:  spec.PrepareMigration,
		ReadinessTimeout:  spec.ReadinessTimeout,
		PreAdmissionPaths: spec.PreAdmissionPaths,
	})
	if err != nil {
		return nil, nil, err
	}
	initialized = true
	return assembly, module, nil
}

// extractBaseConfig 反射提取服务 config struct 匿名内嵌的 BaseConfig；
// 未内嵌即 fail-closed，声明式装配要求通用段单点声明。
func extractBaseConfig(cfg any) (*BaseConfig, error) {
	value := reflect.ValueOf(cfg).Elem()
	valueType := value.Type()
	for index := 0; index < valueType.NumField(); index++ {
		fieldType := valueType.Field(index)
		if fieldType.Anonymous && fieldType.Type == reflect.TypeOf(BaseConfig{}) {
			base, ok := value.Field(index).Addr().Interface().(*BaseConfig)
			if !ok {
				return nil, fmt.Errorf("embedded BaseConfig is not addressable")
			}
			return base, nil
		}
	}
	return nil, fmt.Errorf("config struct %s must embed servicekit.BaseConfig", valueType.Name())
}

type discoveredInfrastructure struct {
	mongo       *MongoConfig
	postgres    *PostgresConfig
	redisScenes map[string]RedisSceneConfig
}

// discoverInfrastructure 按「声明即装配」扫描 config struct：MongoConfig 与
// PostgresConfig 字段（各至多一个）与 RedisSceneConfig 字段（scene 名取
// yaml tag）自动收集。
func discoverInfrastructure(cfg any) (discoveredInfrastructure, error) {
	discovered := discoveredInfrastructure{redisScenes: map[string]RedisSceneConfig{}}
	err := walkInfrastructureFields(reflect.ValueOf(cfg).Elem(), &discovered)
	return discovered, err
}

func walkInfrastructureFields(value reflect.Value, discovered *discoveredInfrastructure) error {
	mongoType := reflect.TypeOf(MongoConfig{})
	postgresType := reflect.TypeOf(PostgresConfig{})
	sceneType := reflect.TypeOf(RedisSceneConfig{})
	valueType := value.Type()
	for index := 0; index < valueType.NumField(); index++ {
		fieldType := valueType.Field(index)
		if !fieldType.IsExported() {
			continue
		}
		field := value.Field(index)
		switch fieldType.Type {
		case mongoType:
			if discovered.mongo != nil {
				return fmt.Errorf(
					"multiple MongoConfig declarations found; assemble extra databases explicitly",
				)
			}
			config, ok := field.Interface().(MongoConfig)
			if !ok {
				return fmt.Errorf("MongoConfig field %s is not readable", fieldType.Name)
			}
			discovered.mongo = &config
		case postgresType:
			if discovered.postgres != nil {
				return fmt.Errorf(
					"multiple PostgresConfig declarations found; assemble extra pools explicitly",
				)
			}
			config, ok := field.Interface().(PostgresConfig)
			if !ok {
				return fmt.Errorf("PostgresConfig field %s is not readable", fieldType.Name)
			}
			discovered.postgres = &config
		case sceneType:
			sceneName := yamlFieldName(fieldType)
			if sceneName == "" {
				return fmt.Errorf(
					"RedisSceneConfig field %s requires a yaml tag as its scene name",
					fieldType.Name,
				)
			}
			if _, exists := discovered.redisScenes[sceneName]; exists {
				return fmt.Errorf("duplicate Redis scene declaration %q", sceneName)
			}
			config, ok := field.Interface().(RedisSceneConfig)
			if !ok {
				return fmt.Errorf("RedisSceneConfig field %s is not readable", fieldType.Name)
			}
			discovered.redisScenes[sceneName] = config
		default:
			if field.Kind() == reflect.Struct {
				if err := walkInfrastructureFields(field, discovered); err != nil {
					return err
				}
			}
		}
	}
	return nil
}

func yamlFieldName(fieldType reflect.StructField) string {
	tag := fieldType.Tag.Get("yaml")
	name := strings.TrimSpace(strings.Split(tag, ",")[0])
	return name
}
