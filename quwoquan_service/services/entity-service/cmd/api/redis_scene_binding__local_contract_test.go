// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md#dec-028
package bootstrap

import (
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"

	"quwoquan_service/runtime/servicekit"
)

var canonicalEnvironments = []string{"alpha", "beta", "gamma", "prod"}

// TestRenderedSnapshotBindsEveryRedisSceneField 是结构对齐的直接取证。
//
// 它用**实际渲染出的四环境配置快照**喂 entity 的解码路径，再把解码后的
// RedisSceneConfig 与同一份快照原文逐字段对照。取证对象不是「某个期望值」而是
// 「快照说了什么、结构读到了什么」是否相等，因此它对形状漂移是敏感的：
// 一旦有人把 config.Redis 改回扁平的 servicekit.RedisSceneConfig，
// `redis: {general: {...}}` 里没有任何键能匹配 mode/addr/db/tls/pool，
// 解码结果整体落到 Go 零值，而快照里 mode=standalone、pool 非零，断言立即为红。
//
// 这正是本次缺陷的形态：扁平结构下 mode 为空字符串，恰好命中 servicekit
// 「未声明 mode 且无地址即 memory」这条**合法**回落，运行期没有任何信号，
// 只能靠这条对照断言关闭。
func TestRenderedSnapshotBindsEveryRedisSceneField(t *testing.T) {
	for _, environment := range canonicalEnvironments {
		raw := renderCanonicalSnapshot(t, environment)
		if err := snapshotGuard(raw); err != nil {
			t.Fatalf("%s rendered snapshot rejected by its own guard: %v", environment, err)
		}

		cfg := &config{}
		if err := yaml.Unmarshal(raw, cfg); err != nil {
			t.Fatalf("%s decode rendered snapshot: %v", environment, err)
		}
		scene := snapshotRedisScenes(t, environment, raw)["general"]
		decoded := cfg.Redis.General

		if decoded.Mode == "" {
			t.Fatalf(
				"%s: redis.general decoded to the Go zero value; the config struct no longer "+
					"matches the snapshot shape and every scene field was silently dropped",
				environment,
			)
		}
		assertSceneField(t, environment, "mode", scene["mode"], decoded.Mode)
		assertSceneField(t, environment, "addr", scene["addr"], decoded.Addr)
		assertSceneField(t, environment, "db", scene["db"], decoded.DB)
		assertSceneField(t, environment, "tls", scene["tls"], decoded.TLS)

		pool, ok := scene["pool"].(map[string]any)
		if !ok {
			t.Fatalf("%s: redis.general.pool is missing from the rendered snapshot", environment)
		}
		assertSceneField(t, environment, "pool.size", pool["size"], decoded.Pool.Size)
		assertSceneField(t, environment, "pool.min_idle", pool["min_idle"], decoded.Pool.MinIdle)
		assertSceneField(
			t, environment, "pool.read_timeout_ms",
			pool["read_timeout_ms"], decoded.Pool.ReadTimeoutMs,
		)
		assertSceneField(
			t, environment, "pool.write_timeout_ms",
			pool["write_timeout_ms"], decoded.Pool.WriteTimeoutMs,
		)
		assertSceneField(
			t, environment, "pool.dial_timeout_ms",
			pool["dial_timeout_ms"], decoded.Pool.DialTimeoutMs,
		)
	}
}

// TestRedisSceneSetAgreesAcrossStructSchemaAndSnapshot 关闭「schema 声明了但
// 代码不消费」这一类 scene：config/schema.yaml 的 scene 集合、config struct 声明
// 的 scene 集合与渲染快照的 redis 键集必须三方相等。
//
// entity 的 rec scene 就是这样长出来的——schema 声明、prod 快照给了
// mode=cluster override，代码却从未装配它。一个没有消费点的 scene 声明是第二
// 真相源，也是本次静默失效的温床。
func TestRedisSceneSetAgreesAcrossStructSchemaAndSnapshot(t *testing.T) {
	declared := structDeclaredRedisScenes(t)
	if len(declared) == 0 {
		t.Fatal("config struct declares no Redis scene")
	}
	if schemaScenes := configSchemaRedisScenes(t); !reflect.DeepEqual(schemaScenes, declared) {
		t.Fatalf(
			"config/schema.yaml declares Redis scenes %v but the config struct declares %v; "+
				"a scene without a consumption point is a second source of truth",
			sortedSceneNames(schemaScenes), sortedSceneNames(declared),
		)
	}
	for _, environment := range canonicalEnvironments {
		raw := renderCanonicalSnapshot(t, environment)
		snapshotScenes := map[string]struct{}{}
		for name := range snapshotRedisScenes(t, environment, raw) {
			snapshotScenes[name] = struct{}{}
		}
		if !reflect.DeepEqual(snapshotScenes, declared) {
			t.Fatalf(
				"%s rendered snapshot carries Redis scenes %v but the config struct declares %v",
				environment, sortedSceneNames(snapshotScenes), sortedSceneNames(declared),
			)
		}
	}
}

// TestRenderedSnapshotFailsClosedWithoutInjectedSceneAddr 锁定「general scene
// 的地址只由环境装配注入」这条契约的两端。
//
// 四环境快照都把 mode 声明为 standalone 且不写 addr，因此缺地址注入在骨架装配
// 期就被判否——包括 alpha：骨架不按地址在场与否推断运行模式，「本环境不接真实
// Redis」只能由 `mode: memory` 显式声明。本服务的准入判据是显式声明之后的第二
// 道：只有 alpha 允许声明 memory。注入 scene 专属地址后 scene 必须解析为
// standalone，并对四环境全部放行。
func TestRenderedSnapshotFailsClosedWithoutInjectedSceneAddr(t *testing.T) {
	for _, environment := range canonicalEnvironments {
		cfg := &config{}
		if err := yaml.Unmarshal(renderCanonicalSnapshot(t, environment), cfg); err != nil {
			t.Fatalf("%s decode rendered snapshot: %v", environment, err)
		}
		if addr := strings.TrimSpace(cfg.Redis.General.Addr); addr != "" {
			t.Fatalf(
				"%s: redis.general.addr is pinned to %q in the snapshot; the physical "+
					"endpoint must stay an environment injection", environment, addr,
			)
		}
		scenes := map[string]servicekit.RedisSceneConfig{"general": cfg.Redis.General}
		if _, _, err := servicekit.NewRedisRouter(scenes); err == nil {
			t.Fatalf(
				"%s: a standalone declaration without ENTITY_REDIS_GENERAL_ADDR must "+
					"fail closed at assembly", environment,
			)
		}

		// 显式关停是唯一合法的「不接真实 Redis」路径，且只有 alpha 可以走。
		closed := cfg.Redis.General
		closed.Mode = servicekit.RedisModeMemory
		router, modes, err := servicekit.NewRedisRouter(
			map[string]servicekit.RedisSceneConfig{"general": closed},
		)
		if err != nil {
			t.Fatalf("%s: an explicit memory declaration must assemble: %v", environment, err)
		}
		t.Cleanup(func() { _ = router.Close() })
		if modes["general"] != servicekit.RedisModeMemory {
			t.Fatalf(
				"%s: explicit memory declaration resolved to %q",
				environment, modes["general"],
			)
		}
		guardErr := requireRealRedisOutsideAlpha(modes["general"], environment)
		if environment == "alpha" {
			if guardErr != nil {
				t.Fatalf("alpha may run without a real Redis: %v", guardErr)
			}
		} else if guardErr == nil {
			t.Fatalf("%s: declaring the general scene closed must fail closed", environment)
		}

		cfg.Redis.General.Addr = "redis:6379"
		scenes["general"] = cfg.Redis.General
		injected, injectedModes, err := servicekit.NewRedisRouter(scenes)
		if err != nil {
			t.Fatalf("%s: injected scene addr must assemble: %v", environment, err)
		}
		t.Cleanup(func() { _ = injected.Close() })
		if injectedModes["general"] != "standalone" {
			t.Fatalf(
				"%s: injected general scene resolved to %q, want standalone",
				environment, injectedModes["general"],
			)
		}
		if err := requireRealRedisOutsideAlpha(injectedModes["general"], environment); err != nil {
			t.Fatalf("%s: injected scene addr must pass admission: %v", environment, err)
		}
	}
}

// TestRetiredFlatRedisInjectionFailsClosed 锁定退役形态的两条拒收路径：
// 无 scene 的 ENTITY_REDIS_* 注入键必须从声明键集消失并被启动期拒收，扁平
// 或带 rec 的快照必须被 snapshotGuard 拒收。只删读取点会让继续注入的部署与
// 继续挂载的旧快照静默回落 memory。
func TestRetiredFlatRedisInjectionFailsClosed(t *testing.T) {
	keys, err := DeclaredEnvKeys()
	if err != nil {
		t.Fatalf("derive declared env keys: %v", err)
	}
	declared := map[string]bool{}
	for _, key := range keys {
		declared[key] = true
	}
	retired := retiredEnvKeys()
	for _, key := range retired {
		if declared[key] {
			t.Fatalf("%s is retired but still declared as an override key", key)
		}
	}
	if !declared["ENTITY_REDIS_GENERAL_ADDR"] || !declared["ENTITY_REDIS_GENERAL_PASSWORD"] {
		t.Fatalf("scene-scoped Redis keys are missing from %v", keys)
	}
	for _, key := range []string{"ENTITY_REDIS_ADDR", "ENTITY_REDIS_PASSWORD", "ENTITY_REDIS_MODE"} {
		if !containsKey(retired, key) {
			t.Fatalf("retired env keys=%v must reject %s", retired, key)
		}
	}
	if err := servicekit.RejectRetiredEnvKeys(retired); err != nil {
		t.Fatalf("a clean process environment must pass: %v", err)
	}
	t.Setenv("ENTITY_REDIS_ADDR", "redis:6379")
	if err := servicekit.RejectRetiredEnvKeys(retired); err == nil {
		t.Fatal("legacy ENTITY_REDIS_ADDR injection must fail closed")
	}

	for name, snapshot := range map[string]string{
		"flat": "redis:\n  mode: standalone\n  addr: redis:6379\n  db: 0\n",
		"rec":  "redis:\n  general:\n    mode: standalone\n  rec:\n    mode: cluster\n",
	} {
		if err := snapshotGuard([]byte(snapshot)); err == nil {
			t.Fatalf("retired %s redis snapshot shape must be rejected", name)
		}
	}
}

// renderCanonicalSnapshot 调用 canonical 渲染器产出该环境的真实配置快照。
// 不使用手写内联 yaml：内联片段只能测 struct 自己，测不到 config/schema.yaml
// 与 struct 的对齐，而这次的缺陷恰好只存在于两者之间。
func renderCanonicalSnapshot(t *testing.T, environment string) []byte {
	t.Helper()
	repoRoot := repositoryRoot(t)
	output := filepath.Join(t.TempDir(), "entity-service.yaml")
	command := exec.Command(
		"python3", filepath.Join(repoRoot, "quwoquan_ops", "cli", "render_runtime_config.py"),
		"--env", environment, "--workload", "entity-service", "--output", output,
	)
	command.Env = append(os.Environ(), "PYTHONDONTWRITEBYTECODE=1")
	if combined, err := command.CombinedOutput(); err != nil {
		t.Fatalf("render %s canonical config: %v\n%s", environment, err, combined)
	}
	raw, err := os.ReadFile(output)
	if err != nil {
		t.Fatalf("read %s canonical config %s: %v", environment, output, err)
	}
	return raw
}

func snapshotRedisScenes(t *testing.T, environment string, raw []byte) map[string]map[string]any {
	t.Helper()
	var document struct {
		Redis map[string]map[string]any `yaml:"redis"`
	}
	if err := yaml.Unmarshal(raw, &document); err != nil {
		t.Fatalf("%s parse rendered redis section: %v", environment, err)
	}
	if len(document.Redis) == 0 {
		t.Fatalf("%s rendered snapshot carries no redis section", environment)
	}
	return document.Redis
}

// structDeclaredRedisScenes 按 servicekit「声明即装配」的同一条规则派生 scene
// 名：config.Redis 下每个 RedisSceneConfig 字段的 yaml tag 即 scene 名。
func structDeclaredRedisScenes(t *testing.T) map[string]struct{} {
	t.Helper()
	redisField, found := reflect.TypeOf(config{}).FieldByName("Redis")
	if !found {
		t.Fatal("config must declare a Redis section")
	}
	sceneType := reflect.TypeOf(servicekit.RedisSceneConfig{})
	scenes := map[string]struct{}{}
	for index := 0; index < redisField.Type.NumField(); index++ {
		field := redisField.Type.Field(index)
		if field.Type != sceneType {
			t.Fatalf(
				"config.Redis field %s is %s, want a per-scene servicekit.RedisSceneConfig; "+
					"a flat scene declaration cannot bind the nested snapshot shape",
				field.Name, field.Type,
			)
		}
		name := strings.TrimSpace(strings.Split(field.Tag.Get("yaml"), ",")[0])
		if name == "" {
			t.Fatalf("config.Redis field %s needs a yaml tag as its scene name", field.Name)
		}
		scenes[name] = struct{}{}
	}
	return scenes
}

func configSchemaRedisScenes(t *testing.T) map[string]struct{} {
	t.Helper()
	path := filepath.Join(
		repositoryRoot(t), "quwoquan_service", "services", "entity-service",
		"config", "schema.yaml",
	)
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	var schema struct {
		Configs []struct {
			Key string `yaml:"key"`
		} `yaml:"configs"`
	}
	if err := yaml.Unmarshal(raw, &schema); err != nil {
		t.Fatalf("parse %s: %v", path, err)
	}
	const prefix = "sys.entity-service.redis."
	scenes := map[string]struct{}{}
	for _, entry := range schema.Configs {
		if !strings.HasPrefix(entry.Key, prefix) {
			continue
		}
		scene, _, found := strings.Cut(strings.TrimPrefix(entry.Key, prefix), ".")
		if !found || scene == "" {
			t.Fatalf("%s declares an unscoped Redis key %s", path, entry.Key)
		}
		scenes[scene] = struct{}{}
	}
	return scenes
}

func assertSceneField(t *testing.T, environment string, field string, snapshot any, decoded any) {
	t.Helper()
	if !reflect.DeepEqual(snapshot, decoded) {
		t.Fatalf(
			"%s: redis.general.%s decoded as %#v but the rendered snapshot declares %#v",
			environment, field, decoded, snapshot,
		)
	}
}

func sortedSceneNames(scenes map[string]struct{}) []string {
	names := make([]string, 0, len(scenes))
	for name := range scenes {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}

func containsKey(keys []string, wanted string) bool {
	for _, key := range keys {
		if key == wanted {
			return true
		}
	}
	return false
}

func repositoryRoot(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for {
		if _, err := os.Stat(
			filepath.Join(dir, "quwoquan_ops", "cli", "render_runtime_config.py"),
		); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Fatal("repository root not found above test directory")
		}
		dir = parent
	}
}
