// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-002
package local_contract

import (
	"reflect"
	"testing"

	bootstrap "quwoquan_service/services/tag-service/cmd/api"
)

// TestDeclaredEnvKeysCoverRetiredHandwrittenHooks 是 DEC-028 要求的迁移等价
// 断言：config struct 声明派生的 env 覆盖键全集必须精确等于预期集合，且必须
// 覆盖被删除的手写钩子（applyEnvOverrides + applyTagRedisEnvOverrides）的每
// 一个键——少一个即部署面覆盖能力静默丢失。
func TestDeclaredEnvKeysCoverRetiredHandwrittenHooks(t *testing.T) {
	keys, err := bootstrap.DeclaredEnvKeys()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// RedisSceneConfig 的 DB 后缀是标准覆盖面的一部分，手写钩子未覆盖它；
	// 声明面是手写面的超集，方向安全（未注入的键不生效）。
	expected := []string{
		"TAG_SERVICE_ADDR",
		"TAG_USER_ACCOUNT_SECURITY_AUTHORITY_BASE_URL",
		"TAG_MONGO_URI",
		"TAG_MONGO_DATABASE",
		"TAG_REDIS_GENERAL_MODE",
		"TAG_REDIS_GENERAL_ADDR",
		"TAG_REDIS_GENERAL_ADDRS",
		"TAG_REDIS_GENERAL_PASSWORD",
		"TAG_REDIS_GENERAL_DB",
		"TAG_REDIS_GENERAL_TLS",
	}
	if !reflect.DeepEqual(keys, expected) {
		t.Fatalf("declared env keys drifted:\n got %v\nwant %v", keys, expected)
	}

	retiredHandwrittenKeys := []string{
		"TAG_SERVICE_ADDR",
		"TAG_MONGO_URI",
		"TAG_MONGO_DATABASE",
		"TAG_REDIS_GENERAL_MODE",
		"TAG_REDIS_GENERAL_ADDR",
		"TAG_REDIS_GENERAL_ADDRS",
		"TAG_REDIS_GENERAL_PASSWORD",
		"TAG_REDIS_GENERAL_TLS",
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
