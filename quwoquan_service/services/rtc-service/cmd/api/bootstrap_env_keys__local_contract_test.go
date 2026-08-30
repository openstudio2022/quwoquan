// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-002
package main

import (
	"reflect"
	"testing"
)

// TestDeclaredEnvKeysCoverRetiredHandwrittenHooks 是 DEC-028 要求的迁移等价
// 断言：声明派生的 env 覆盖键全集必须精确等于预期集合，且必须覆盖被删除的
// 手写 applyEnvOverrides / applyRedisSceneEnv 的每一个键。Mongo 段与共享
// Redis 兜底已按 DEC-028 的数据面键裁决收敛为 RTC_ 前缀。
func TestDeclaredEnvKeysCoverRetiredHandwrittenHooks(t *testing.T) {
	keys, err := DeclaredEnvKeys()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// DB 后缀是 RedisSceneConfig 标准覆盖面的一部分，手写钩子未覆盖它；
	// 声明面是手写面的超集，方向安全（未注入的键不生效）。
	expected := []string{
		"RTC_SERVICE_ADDR",
		"RTC_USER_ACCOUNT_SECURITY_AUTHORITY_BASE_URL",
		"RTC_MONGO_URI",
		"RTC_MONGO_DATABASE",
		"RTC_REDIS_REALTIME_MODE",
		"RTC_REDIS_REALTIME_ADDR",
		"RTC_REDIS_REALTIME_ADDRS",
		"RTC_REDIS_REALTIME_PASSWORD",
		"RTC_REDIS_REALTIME_DB",
		"RTC_REDIS_REALTIME_TLS",
		"RTC_REDIS_GENERAL_MODE",
		"RTC_REDIS_GENERAL_ADDR",
		"RTC_REDIS_GENERAL_ADDRS",
		"RTC_REDIS_GENERAL_PASSWORD",
		"RTC_REDIS_GENERAL_DB",
		"RTC_REDIS_GENERAL_TLS",
		"RTC_REDIS_ADDR",
	}
	if !reflect.DeepEqual(keys, expected) {
		t.Fatalf("declared env keys drifted:\n got %v\nwant %v", keys, expected)
	}

	retiredHandwrittenKeys := []string{
		"RTC_SERVICE_ADDR",
		"RTC_MONGO_URI",
		"RTC_MONGO_DATABASE",
		"RTC_REDIS_REALTIME_MODE",
		"RTC_REDIS_REALTIME_ADDR",
		"RTC_REDIS_REALTIME_ADDRS",
		"RTC_REDIS_REALTIME_PASSWORD",
		"RTC_REDIS_REALTIME_TLS",
		"RTC_REDIS_GENERAL_MODE",
		"RTC_REDIS_GENERAL_ADDR",
		"RTC_REDIS_GENERAL_ADDRS",
		"RTC_REDIS_GENERAL_PASSWORD",
		"RTC_REDIS_GENERAL_TLS",
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

	// 无前缀的 MONGO_URI / REDIS_ADDR 已退场：service-core 之外的独立进程
	// 同样不保留无前缀数据面键，否则同一台宿主上多个服务的注入会互相串。
	for _, unprefixed := range []string{"MONGO_URI", "MONGO_DATABASE", "REDIS_ADDR"} {
		if declared[unprefixed] {
			t.Fatalf("unprefixed data-plane key %s must not be readable anymore", unprefixed)
		}
	}
}

// TestSharedRedisAddrFallbackKeepsSceneSpecificPriority 锁定 RTC_REDIS_ADDR 的
// 部署面兜底语义：compose 与 prod plane 为两个 scene 共享注入它，scene 专属
// 地址优先，两者都缺时该 scene 落 memory 模式。
func TestSharedRedisAddrFallbackKeepsSceneSpecificPriority(t *testing.T) {
	cfg := &config{}
	cfg.Redis.General.Addr = "general-specific:6379"
	cfg.Redis.SharedAddr = "shared:6379"

	scenes := resolveRedisScenes(cfg)
	if scenes["general"].Addr != "general-specific:6379" {
		t.Fatalf("scene-specific addr must win, got %q", scenes["general"].Addr)
	}
	if scenes["realtime"].Addr != "shared:6379" {
		t.Fatalf("empty scene must take the shared fallback, got %q", scenes["realtime"].Addr)
	}
	if scenes["rec"].Addr != scenes["general"].Addr {
		t.Fatalf("rec scene must reuse general, got %q", scenes["rec"].Addr)
	}

	blank := &config{}
	scenes = resolveRedisScenes(blank)
	if scenes["realtime"].Addr != "" {
		t.Fatalf("no declaration and no fallback must stay empty, got %q", scenes["realtime"].Addr)
	}
}
