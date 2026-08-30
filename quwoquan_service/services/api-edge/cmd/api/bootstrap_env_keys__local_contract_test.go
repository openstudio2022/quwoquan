// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-002
package bootstrap

import (
	"reflect"
	"testing"
)

// TestDeclaredEnvKeysCoverRetiredHandwrittenReads 是 DEC-028 要求的迁移等价
// 断言：声明派生的 env 覆盖键全集必须精确等于预期集合，且必须覆盖迁移前
// 手写读取过的每一个 api-edge 配置键。
//
// 迁移前 api-edge 的 runtimeConfig 没有任何 env tag：配置全部来自渲染快照，
// 整个配置层只有两处裸 os.Getenv/os.LookupEnv——admission Redis 密码与
// rollout 分配密钥，二者都是 environments/prod/config.yaml 的 secretRef。
// 迁移把它们上收成字段声明，键名字面不变。
func TestDeclaredEnvKeysCoverRetiredHandwrittenReads(t *testing.T) {
	keys, err := DeclaredEnvKeys()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	expected := []string{
		"API_EDGE_SERVICE_ADDR",
		"API_EDGE_USER_ACCOUNT_SECURITY_AUTHORITY_BASE_URL",
		"API_EDGE_REDIS_PASSWORD",
		"API_EDGE_ROLLOUT_ALLOCATION_KEY",
	}
	if !reflect.DeepEqual(keys, expected) {
		t.Fatalf("declared env keys drifted:\n got %v\nwant %v", keys, expected)
	}

	declared := make(map[string]bool, len(keys))
	for _, key := range keys {
		declared[key] = true
	}
	// 迁移前实际被读取的两个 secretRef 键必须逐字保留：它们由部署面按
	// environments/prod/config.yaml 的 secretRefs 注入，键名漂移会让密码与
	// 分配密钥静默变空，进而让准入与 rollout 静默改变行为。
	for _, key := range []string{
		"API_EDGE_REDIS_PASSWORD",
		"API_EDGE_ROLLOUT_ALLOCATION_KEY",
	} {
		if !declared[key] {
			t.Fatalf("retired handwritten read %s lost its declaration", key)
		}
	}

	// 无服务前缀的数据面键一律不可读：api-edge 与其余模块同进程运行在
	// service-core 里，共享一个无前缀键等于共享一个存储实例（DEC-028）。
	for _, unprefixed := range []string{
		"REDIS_PASSWORD",
		"REDIS_ADDR",
		"ROLLOUT_ALLOCATION_KEY",
	} {
		if declared[unprefixed] {
			t.Fatalf("unprefixed data-plane key %s must not be readable", unprefixed)
		}
	}
}
