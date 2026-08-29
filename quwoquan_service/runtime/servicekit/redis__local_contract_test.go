package servicekit

import (
	"strings"
	"testing"
)

func TestNewRedisRouterRequiresAtLeastOneScene(t *testing.T) {
	if _, _, err := NewRedisRouter(nil); err == nil {
		t.Fatal("expected error for empty scene map")
	}
}

func TestNewRedisRouterRejectsBlankSceneName(t *testing.T) {
	_, _, err := NewRedisRouter(map[string]RedisSceneConfig{
		"  ": {Mode: RedisModeMemory},
	})
	if err == nil {
		t.Fatal("expected error for blank scene name")
	}
}

// 运行模式只由 mode 表达。缺声明时不再按地址在场与否推断拓扑：地址为空既可能是
// 「本环境不接真实 Redis」也可能是「漏了地址注入」，两者后果相反，代码不能替
// 声明者选一个。
//
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/explicit-semantics-no-implicit-inference/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/explicit-semantics-no-implicit-inference/spec.md#gwt-001.t2
func TestDeclaredModeRejectsMissingDeclaration(t *testing.T) {
	cases := map[string]RedisSceneConfig{
		"nothing declared":           {},
		"addr injected without mode": {Addr: "redis:6379"},
		"addrs injected without mode": {
			Addrs: []string{"a:6379", "b:6379", "c:6379"},
		},
	}
	for name, sceneConfig := range cases {
		t.Run(name, func(t *testing.T) {
			_, err := sceneConfig.DeclaredMode()
			if err == nil {
				t.Fatal("expected missing mode declaration to be rejected")
			}
			// 判否文本要给出全部合法取值与可写声明的位置，否则读者既不知道能写
			// 什么，也不知道该改哪个文件。
			for _, mode := range []string{
				RedisModeMemory, RedisModeStandalone, RedisModeCluster,
			} {
				if !strings.Contains(err.Error(), mode) {
					t.Errorf("error must list %s as a legal value: %v", mode, err)
				}
			}
			if !strings.Contains(err.Error(), "config-defaults.yaml") {
				t.Fatalf("error must point at the declaration sites: %v", err)
			}
		})
	}
}

// memory 是「本环境不接真实 Redis」的唯一合法表达，且必须与地址缺席一致。
func TestDeclaredModeAcceptsExplicitMemoryWithoutAddress(t *testing.T) {
	mode, err := (RedisSceneConfig{Mode: "Memory"}).DeclaredMode()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if mode != RedisModeMemory {
		t.Fatalf("expected normalized memory, got %s", mode)
	}
}

// 两处声明互相矛盾时判否：挑地址会让声明的关停失效，挑 memory 会让注入的地址
// 静默失效，两者都是代码替声明者做决定。
//
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/explicit-semantics-no-implicit-inference/spec.md#gwt-001.t3
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/explicit-semantics-no-implicit-inference/spec.md#gwt-001.t4
func TestDeclaredModeRejectsContradictoryDeclarations(t *testing.T) {
	cases := map[string]RedisSceneConfig{
		"memory with addr":      {Mode: RedisModeMemory, Addr: "redis:6379"},
		"memory with addrs":     {Mode: RedisModeMemory, Addrs: []string{"a:6379"}},
		"standalone with addrs": {Mode: RedisModeStandalone, Addr: "redis:6379", Addrs: []string{"a:6379"}},
		"cluster with both":     {Mode: RedisModeCluster, Addr: "redis:6379", Addrs: []string{"a:6379"}},
		"unsupported mode":      {Mode: "sentinel", Addr: "redis:6379"},
	}
	for name, sceneConfig := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := sceneConfig.DeclaredMode(); err == nil {
				t.Fatal("expected contradictory declaration to be rejected")
			}
		})
	}
}

// 声明了物理拓扑却缺配套地址是注入缺陷，不是有意关停。静默回落 memory 会让多
// 副本各自持有一份不共享、重启即丢的「Redis」，而幂等键、分布式锁与会话都建立
// 在跨副本可见的前提上——那种失效在运行期没有任何信号。
//
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/explicit-semantics-no-implicit-inference/spec.md#gwt-002.t1
func TestNewRedisRouterRejectsDeclaredTopologyWithoutAddress(t *testing.T) {
	cases := map[string]RedisSceneConfig{
		"standalone without addr": {Mode: RedisModeStandalone},
		"cluster without addrs":   {Mode: RedisModeCluster},
		// prod plane 的现实形态：快照声明 cluster，环境只注入单点 addr。
		"cluster with only a single addr": {Mode: RedisModeCluster, Addr: "redis:6379"},
		"mode never declared":             {},
	}
	for name, sceneConfig := range cases {
		t.Run(name, func(t *testing.T) {
			_, _, err := NewRedisRouter(map[string]RedisSceneConfig{
				"general": sceneConfig,
			})
			if err == nil {
				t.Fatal("expected the scene to be rejected at assembly time")
			}
			if !strings.Contains(err.Error(), "general") {
				t.Fatalf("error must name the offending scene: %v", err)
			}
		})
	}
}

// 判否文本必须同时给出两条出路。只说「缺地址」时读者会默认去补地址，而「本环境
// 本就不接真实 Redis」同样是合法答案，且它才是那些从未注入过地址的环境的正解。
//
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/explicit-semantics-no-implicit-inference/spec.md#gwt-002.t2
func TestDeclaredModeRejectionNamesBothRemedies(t *testing.T) {
	for name, tc := range map[string]struct {
		sceneConfig RedisSceneConfig
		wantInject  string
		wantRedecl  string
	}{
		"standalone without addr": {
			sceneConfig: RedisSceneConfig{Mode: RedisModeStandalone},
			wantInject:  "inject the addr",
			wantRedecl:  "mode=" + RedisModeMemory,
		},
		"cluster without addrs": {
			sceneConfig: RedisSceneConfig{Mode: RedisModeCluster},
			wantInject:  "inject the cluster addrs",
			wantRedecl:  "mode=" + RedisModeMemory,
		},
		"cluster with only a single addr": {
			sceneConfig: RedisSceneConfig{Mode: RedisModeCluster, Addr: "redis:6379"},
			wantInject:  "inject the cluster addrs",
			wantRedecl:  "mode=" + RedisModeStandalone,
		},
	} {
		t.Run(name, func(t *testing.T) {
			_, err := tc.sceneConfig.DeclaredMode()
			if err == nil {
				t.Fatal("expected the incomplete declaration to be rejected")
			}
			if !strings.Contains(err.Error(), tc.wantInject) {
				t.Errorf("error must offer the injection remedy %q: %v", tc.wantInject, err)
			}
			if !strings.Contains(err.Error(), tc.wantRedecl) {
				t.Errorf("error must offer the re-declaration remedy %q: %v", tc.wantRedecl, err)
			}
		})
	}
}

// 段间复用只有「整段缺席即复用」一条规则。部分声明不触发复用——否则会把这一段的
// mode 和另一段的地址拼成一份没人声明过的配置，出问题时没有任何文件能解释生效值。
//
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/explicit-semantics-no-implicit-inference/spec.md#gwt-004.t1
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/explicit-semantics-no-implicit-inference/spec.md#gwt-004.t2
func TestIsUndeclaredSeparatesWholeSceneAbsenceFromPartialDeclaration(t *testing.T) {
	if !(RedisSceneConfig{}).IsUndeclared() {
		t.Fatal("an untouched scene config must count as undeclared")
	}
	partial := map[string]RedisSceneConfig{
		"mode only":     {Mode: RedisModeStandalone},
		"addr only":     {Addr: "redis:6379"},
		"addrs only":    {Addrs: []string{"a:6379"}},
		"password only": {Password: "secret"},
		"db only":       {DB: 3},
		"tls only":      {TLS: true},
	}
	for name, sceneConfig := range partial {
		t.Run(name, func(t *testing.T) {
			if sceneConfig.IsUndeclared() {
				t.Fatal("a partially declared scene must not be treated as absent")
			}
			// 不复用之后这一段按自身声明校验，而这些声明都不成套：缺 mode 或
			// 声明了 standalone 却没有地址，两者都必须判否。
			if _, err := sceneConfig.DeclaredMode(); err == nil {
				t.Fatalf("an incomplete scene must not resolve to a mode: %+v", sceneConfig)
			}
		})
	}
	pool := RedisSceneConfig{}
	pool.Pool.Size = 8
	if pool.IsUndeclared() {
		t.Fatal("a declared pool must keep the scene from being reused wholesale")
	}
}

// SceneConfig 不得把判否吞掉：错误随返回值一起交出，且解析结果保留声明的 mode，
// 避免调用方读到一个「看起来正常」的 memory。
func TestSceneConfigSurfacesRejectionAlongsideDeclaredMode(t *testing.T) {
	resolved, err := (RedisSceneConfig{Mode: RedisModeCluster}).SceneConfig()
	if err == nil {
		t.Fatal("expected cluster without seeds to be rejected")
	}
	if resolved.Mode != RedisModeCluster {
		t.Fatalf("expected declared mode to survive, got %s", resolved.Mode)
	}
}

func TestSceneConfigKeepsDeclaredPhysicalTopology(t *testing.T) {
	standalone := RedisSceneConfig{Mode: RedisModeStandalone, Addr: "redis.internal:6379", DB: 3}
	resolved, err := standalone.SceneConfig()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resolved.Mode != RedisModeStandalone || resolved.Addr != "redis.internal:6379" || resolved.DB != 3 {
		t.Fatalf("unexpected standalone resolution: %+v", resolved)
	}
	cluster := RedisSceneConfig{Mode: "Cluster", Addrs: []string{"a:6379", "b:6379"}}
	resolved, err = cluster.SceneConfig()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resolved.Mode != RedisModeCluster || len(resolved.Addrs) != 2 {
		t.Fatalf("unexpected cluster resolution: %+v", resolved)
	}
}

func TestNewRedisRouterReturnsDeclaredSceneModes(t *testing.T) {
	router, sceneModes, err := NewRedisRouter(map[string]RedisSceneConfig{
		"general": {Mode: RedisModeMemory},
		"cache":   {Mode: RedisModeMemory},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if router == nil {
		t.Fatal("expected a constructed router")
	}
	if sceneModes["general"] != RedisModeMemory || sceneModes["cache"] != RedisModeMemory {
		t.Fatalf("unexpected scene modes: %v", sceneModes)
	}
	if _, declared := sceneModes["undeclared"]; declared {
		t.Fatal("scene modes must only cover caller-declared scenes")
	}
	if _, ok := router.LookupScene("general"); !ok {
		t.Fatal("expected declared scene to be routable")
	}
}
