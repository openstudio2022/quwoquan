// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-002
package bootstrap

import (
	"reflect"
	"testing"
)

// TestDeclaredEnvKeysCoverRetiredHandwrittenHooks 是 DEC-028 要求的迁移等价
// 断言：声明派生的 env 覆盖键全集必须精确等于预期集合，且必须覆盖被删除的
// 手写 applyEnvOverrides / applyRedisSceneEnv 的每一个键。Mongo 段已按
// DEC-028 的数据面键裁决收敛为 CHAT_ 前缀（同进程多模块不得共享存储实例键）；
// RELIABLE_TASK_* 与跨服务 *_BASE_URL 是共享契约键，保持无服务前缀。
func TestDeclaredEnvKeysCoverRetiredHandwrittenHooks(t *testing.T) {
	keys, err := DeclaredEnvKeys()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// DB 后缀是 RedisSceneConfig 标准覆盖面的一部分，手写钩子未覆盖它；
	// 声明面是手写面的超集，方向安全（未注入的键不生效）。
	expected := []string{
		"CHAT_SERVICE_ADDR",
		"CHAT_USER_ACCOUNT_SECURITY_AUTHORITY_BASE_URL",
		"CHAT_MONGO_URI",
		"CHAT_MONGO_DATABASE",
		"CHAT_REDIS_REALTIME_MODE",
		"CHAT_REDIS_REALTIME_ADDR",
		"CHAT_REDIS_REALTIME_ADDRS",
		"CHAT_REDIS_REALTIME_PASSWORD",
		"CHAT_REDIS_REALTIME_DB",
		"CHAT_REDIS_REALTIME_TLS",
		"CHAT_REDIS_GENERAL_MODE",
		"CHAT_REDIS_GENERAL_ADDR",
		"CHAT_REDIS_GENERAL_ADDRS",
		"CHAT_REDIS_GENERAL_PASSWORD",
		"CHAT_REDIS_GENERAL_DB",
		"CHAT_REDIS_GENERAL_TLS",
		"CHAT_REDIS_RELIABLE_TASK_MODE",
		"CHAT_REDIS_RELIABLE_TASK_ADDR",
		"CHAT_REDIS_RELIABLE_TASK_ADDRS",
		"CHAT_REDIS_RELIABLE_TASK_PASSWORD",
		"CHAT_REDIS_RELIABLE_TASK_DB",
		"CHAT_REDIS_RELIABLE_TASK_TLS",
		"USER_SERVICE_BASE_URL",
		"CIRCLE_SERVICE_BASE_URL",
		"GATEWAY_BASE_URL",
		"CONTENT_SERVICE_BASE_URL",
		"CHAT_GROUP_AVATAR_CDN_BASE_URL",
		"CHAT_GROUP_AVATAR_LOCAL_MEDIA_ROOT",
		"RUNTIME_SYNC_PATCH_TTL_HOURS",
		"RELIABLE_TASK_READY_INDEX_ENABLED",
		"RELIABLE_TASK_READY_INDEX_STREAM",
		"RELIABLE_TASK_READY_INDEX_GROUP",
		"RELIABLE_TASK_READY_INDEX_QUEUE",
	}
	if !reflect.DeepEqual(keys, expected) {
		t.Fatalf("declared env keys drifted:\n got %v\nwant %v", keys, expected)
	}

	retiredHandwrittenKeys := []string{
		"CHAT_SERVICE_ADDR",
		"CHAT_MONGO_URI",
		"CHAT_MONGO_DATABASE",
		"CHAT_REDIS_REALTIME_MODE",
		"CHAT_REDIS_REALTIME_ADDR",
		"CHAT_REDIS_REALTIME_ADDRS",
		"CHAT_REDIS_REALTIME_PASSWORD",
		"CHAT_REDIS_REALTIME_TLS",
		"CHAT_REDIS_GENERAL_MODE",
		"CHAT_REDIS_GENERAL_ADDR",
		"CHAT_REDIS_GENERAL_ADDRS",
		"CHAT_REDIS_GENERAL_PASSWORD",
		"CHAT_REDIS_GENERAL_TLS",
		"CHAT_REDIS_RELIABLE_TASK_MODE",
		"CHAT_REDIS_RELIABLE_TASK_ADDR",
		"CHAT_REDIS_RELIABLE_TASK_ADDRS",
		"CHAT_REDIS_RELIABLE_TASK_PASSWORD",
		"CHAT_REDIS_RELIABLE_TASK_TLS",
		"USER_SERVICE_BASE_URL",
		"CIRCLE_SERVICE_BASE_URL",
		"GATEWAY_BASE_URL",
		"CONTENT_SERVICE_BASE_URL",
		"CHAT_GROUP_AVATAR_CDN_BASE_URL",
		"CHAT_GROUP_AVATAR_LOCAL_MEDIA_ROOT",
		"RUNTIME_SYNC_PATCH_TTL_HOURS",
		"RELIABLE_TASK_READY_INDEX_ENABLED",
		"RELIABLE_TASK_READY_INDEX_STREAM",
		"RELIABLE_TASK_READY_INDEX_GROUP",
		"RELIABLE_TASK_READY_INDEX_QUEUE",
	}
	declared := make(map[string]bool, len(keys))
	for _, key := range keys {
		declared[key] = true
	}
	for _, key := range retiredHandwrittenKeys {
		if !declared[key] {
			t.Fatalf("retired handwritten override %s lost its declaration", key)
		}
	}

	// 无前缀的共享 REDIS_ADDR 兜底已随迁移退场：三个 scene 在 compose、
	// prod plane 与 gamma mirror 都各自注入物理地址，保留兜底就等于给
	// 同一个读取点留两条注入轨。
	if declared["REDIS_ADDR"] {
		t.Fatal("REDIS_ADDR must not be readable by chat-service anymore")
	}
}

// TestReliableTaskRedisSceneFallsBackToGeneral 锁定 scene 装配语义：未声明
// 任何物理组网的 reliable_task 复用 general，rec 恒等于 general。
func TestReliableTaskRedisSceneFallsBackToGeneral(t *testing.T) {
	cfg := &config{}
	cfg.Redis.General.Addr = "general:6379"
	cfg.Redis.Realtime.Addr = "realtime:6379"

	scenes := resolveRedisScenes(cfg)
	if scenes["reliabletask"].Addr != "general:6379" {
		t.Fatalf("undeclared reliable task scene must reuse general, got %q", scenes["reliabletask"].Addr)
	}
	if scenes["rec"].Addr != "general:6379" {
		t.Fatalf("rec scene must reuse general, got %q", scenes["rec"].Addr)
	}

	cfg.Redis.ReliableTask.Addr = "reliabletask:6379"
	scenes = resolveRedisScenes(cfg)
	if scenes["reliabletask"].Addr != "reliabletask:6379" {
		t.Fatalf("declared reliable task scene must win, got %q", scenes["reliabletask"].Addr)
	}
	if scenes["realtime"].Addr != "realtime:6379" {
		t.Fatalf("realtime scene must stay independent, got %q", scenes["realtime"].Addr)
	}
}

// TestValidateChatConfigKeepsFailClosedBoundaries 锁定迁移前散落在 main.go 与
// chatconfig 里的边界：authority origin/超时档位与三个跨服务依赖的 origin
// 形态，任一违反都必须在装配前失败。
func TestValidateChatConfigKeepsFailClosedBoundaries(t *testing.T) {
	valid := func() *config {
		cfg := &config{}
		cfg.UserAccountSecurityAuthority.BaseURL = "http://user-service:18081"
		cfg.UserAccountSecurityAuthority.TimeoutMs = 500
		cfg.Dependencies.UserServiceBaseURL = "http://user-service:18081"
		cfg.Dependencies.CircleServiceBaseURL = "http://circle-service:18082"
		cfg.Dependencies.ContentServiceBaseURL = "http://content-service:18080"
		return cfg
	}
	if err := validateChatConfig(valid()); err != nil {
		t.Fatalf("valid configuration must pass: %v", err)
	}

	// 圈子读路径既可以直连服务，也可以挂在网关后面：两个键都是既有注入点。
	gatewayOnly := valid()
	gatewayOnly.Dependencies.CircleServiceBaseURL = ""
	gatewayOnly.Dependencies.GatewayBaseURL = "http://api-edge:18000"
	if err := validateChatConfig(gatewayOnly); err != nil {
		t.Fatalf("gateway fallback must remain accepted: %v", err)
	}

	for name, mutate := range map[string]func(*config){
		"missing authority origin": func(c *config) { c.UserAccountSecurityAuthority.BaseURL = "" },
		"authority origin with path": func(c *config) {
			c.UserAccountSecurityAuthority.BaseURL = "https://user-service.internal/internal/user"
		},
		"missing authority timeout":    func(c *config) { c.UserAccountSecurityAuthority.TimeoutMs = 0 },
		"authority timeout below min":  func(c *config) { c.UserAccountSecurityAuthority.TimeoutMs = 49 },
		"authority timeout above max":  func(c *config) { c.UserAccountSecurityAuthority.TimeoutMs = 5001 },
		"missing user dependency":      func(c *config) { c.Dependencies.UserServiceBaseURL = "" },
		"missing circle and gateway":   func(c *config) { c.Dependencies.CircleServiceBaseURL = "" },
		"missing content dependency":   func(c *config) { c.Dependencies.ContentServiceBaseURL = "" },
		"content dependency with path": func(c *config) { c.Dependencies.ContentServiceBaseURL = "http://content-service:18080/media" },
	} {
		t.Run(name, func(t *testing.T) {
			cfg := valid()
			mutate(cfg)
			if err := validateChatConfig(cfg); err == nil {
				t.Fatal("invalid configuration must fail closed")
			}
		})
	}
}

// TestSnapshotGuardRejectsRetiredRuntimeAuthSection 锁定退役配置段拒收：
// authority 的配置面已上收到通用段，旧形状的快照必须在 env 覆盖之前被拒。
func TestSnapshotGuardRejectsRetiredRuntimeAuthSection(t *testing.T) {
	retired := []byte("runtime:\n  auth:\n    account_security_authority:\n      timeout_ms: 500\n")
	if err := snapshotGuard(retired); err == nil {
		t.Fatal("retired runtime.auth section must be rejected")
	}

	current := []byte("user_account_security_authority:\n  base_url: http://user-service:18081\n  timeout_ms: 500\nruntime:\n  sync:\n    patch_ttl_hours: 720\n")
	if err := snapshotGuard(current); err != nil {
		t.Fatalf("current snapshot shape must pass: %v", err)
	}
}
