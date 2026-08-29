// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-002
package local_contract

import (
	"reflect"
	"testing"

	bootstrap "quwoquan_service/services/circle-service/cmd/api"
)

// TestDeclaredEnvKeysCoverRetiredHandwrittenHooks 是 DEC-028 要求的迁移等价
// 断言：config struct 声明派生的 env 覆盖键全集必须精确等于预期集合，且必须
// 覆盖被删除的手写 applyEnvOverrides 的每一个键——少一个即部署面覆盖能力
// 静默丢失。Redis 段沿用历史键名 CIRCLE_REDIS_*（非 CIRCLE_REDIS_GENERAL_*）。
func TestDeclaredEnvKeysCoverRetiredHandwrittenHooks(t *testing.T) {
	keys, err := bootstrap.DeclaredEnvKeys()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// MODE/ADDRS/TLS 是 RedisSceneConfig 标准覆盖面的一部分，手写钩子未覆盖
	// 它们；声明面是手写面的超集，方向安全（未注入的键不生效）。
	expected := []string{
		"CIRCLE_SERVICE_ADDR",
		"CIRCLE_USER_ACCOUNT_SECURITY_AUTHORITY_BASE_URL",
		"CIRCLE_MONGO_URI",
		"CIRCLE_MONGO_DATABASE",
		"CIRCLE_REDIS_GENERAL_MODE",
		"CIRCLE_REDIS_GENERAL_ADDR",
		"CIRCLE_REDIS_GENERAL_ADDRS",
		"CIRCLE_REDIS_GENERAL_PASSWORD",
		"CIRCLE_REDIS_GENERAL_DB",
		"CIRCLE_REDIS_GENERAL_TLS",
		// 服务出口共享键：被调服务对所有调用方是同一地址，因此部署面按
		// 无前缀键注入，声明面用 envAbsolute 对齐。
		"CONTENT_SERVICE_BASE_URL",
		"CHAT_SERVICE_BASE_URL",
		"ENTITY_SERVICE_BASE_URL",
		"USER_SERVICE_BASE_URL",
	}
	if !reflect.DeepEqual(keys, expected) {
		t.Fatalf("declared env keys drifted:\n got %v\nwant %v", keys, expected)
	}

	retiredHandwrittenKeys := []string{
		"CIRCLE_SERVICE_ADDR",
		"CIRCLE_MONGO_URI",
		"CIRCLE_MONGO_DATABASE",
		"CIRCLE_REDIS_GENERAL_ADDR",
		"CIRCLE_REDIS_GENERAL_PASSWORD",
		"CIRCLE_REDIS_GENERAL_DB",
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
}
