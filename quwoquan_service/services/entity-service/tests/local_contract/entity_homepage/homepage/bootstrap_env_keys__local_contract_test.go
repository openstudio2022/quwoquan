// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-002
package local_contract

import (
	"reflect"
	"testing"

	bootstrap "quwoquan_service/services/entity-service/cmd/api"
)

// TestDeclaredEnvKeysCoverRetiredHandwrittenHooks 是 DEC-028 要求的迁移等价
// 断言：声明派生的 env 覆盖键全集必须精确等于预期集合，且必须覆盖被删除的
// getenvOrDefault 覆盖点的每一个键。CONTENT_SERVICE_* 是跨服务共享的无前缀
// 契约键，保持 envAbsolute 形态。
func TestDeclaredEnvKeysCoverRetiredHandwrittenHooks(t *testing.T) {
	keys, err := bootstrap.DeclaredEnvKeys()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Redis 键是 scene 专属形态 ENTITY_REDIS_GENERAL_*，与 search/notification
	// 等已迁移服务同形态：配置快照按 scene 嵌套，注入面必须能逐 scene 定址，
	// 否则单一 ENTITY_REDIS_ADDR 无法表达「哪个 scene 的地址」。
	expected := []string{
		"ENTITY_SERVICE_ADDR",
		"ENTITY_USER_ACCOUNT_SECURITY_AUTHORITY_BASE_URL",
		"ENTITY_MONGO_URI",
		"ENTITY_MONGO_DATABASE",
		"ENTITY_REDIS_GENERAL_MODE",
		"ENTITY_REDIS_GENERAL_ADDR",
		"ENTITY_REDIS_GENERAL_ADDRS",
		"ENTITY_REDIS_GENERAL_PASSWORD",
		"ENTITY_REDIS_GENERAL_DB",
		"ENTITY_REDIS_GENERAL_TLS",
		"CONTENT_SERVICE_BASE_URL",
		"CONTENT_SERVICE_OBJECT_INTERSECTIONS_PATH",
	}
	if !reflect.DeepEqual(keys, expected) {
		t.Fatalf("declared env keys drifted:\n got %v\nwant %v", keys, expected)
	}

	retiredOverridePoints := []string{
		"ENTITY_SERVICE_ADDR",
		"ENTITY_USER_ACCOUNT_SECURITY_AUTHORITY_BASE_URL",
		"ENTITY_MONGO_URI",
		"ENTITY_MONGO_DATABASE",
		"ENTITY_REDIS_GENERAL_ADDR",
		"ENTITY_REDIS_GENERAL_PASSWORD",
		"CONTENT_SERVICE_BASE_URL",
		"CONTENT_SERVICE_OBJECT_INTERSECTIONS_PATH",
	}
	declared := make(map[string]bool, len(keys))
	for _, key := range keys {
		declared[key] = true
	}
	for _, key := range retiredOverridePoints {
		if !declared[key] {
			t.Fatalf("retired override point %s lost its declaration", key)
		}
	}
}
