package bootstrap

import (
	"sort"
	"strings"
	"testing"
)

// 声明式 config struct 派生的 env 覆盖键必须逐一覆盖被删除的手写覆盖钩子，
// 否则部署面注入会静默失效。retiredHandwrittenKeys 是迁移前 ApplyEnvOverrides
// 与 applyRedisSceneEnv 实际读取的键集。
//
// 无前缀的 MONGO_URI / MONGO_DATABASE 不在其中：它们是与 INTEGRATION_ 前缀键
// 并存的第二轨，部署面从未注入，迁移时按契约单轨删除。
func TestDeclaredEnvKeysCoverRetiredHandwrittenOverrides(t *testing.T) {
	retiredHandwrittenKeys := []string{
		"INTEGRATION_SERVICE_ADDR",
		"INTEGRATION_MONGO_URI",
		"INTEGRATION_MONGO_DATABASE",
		"INTEGRATION_LOCATION_DEFAULT_LATITUDE",
		"INTEGRATION_LOCATION_DEFAULT_LONGITUDE",
		"INTEGRATION_REDIS_GENERAL_MODE",
		"INTEGRATION_REDIS_GENERAL_ADDR",
		"INTEGRATION_REDIS_GENERAL_ADDRS",
		"INTEGRATION_REDIS_GENERAL_PASSWORD",
		"INTEGRATION_REDIS_GENERAL_DB",
		"INTEGRATION_REDIS_GENERAL_TLS",
		"INTEGRATION_REDIS_REC_MODE",
		"INTEGRATION_REDIS_REC_ADDR",
		"INTEGRATION_REDIS_REC_ADDRS",
		"INTEGRATION_REDIS_REC_PASSWORD",
		"INTEGRATION_REDIS_REC_DB",
		"INTEGRATION_REDIS_REC_TLS",
	}

	declared, err := DeclaredEnvKeys()
	if err != nil {
		t.Fatalf("derive declared env keys: %v", err)
	}
	declaredSet := make(map[string]struct{}, len(declared))
	for _, key := range declared {
		declaredSet[key] = struct{}{}
	}
	for _, key := range retiredHandwrittenKeys {
		if _, found := declaredSet[key]; !found {
			sort.Strings(declared)
			t.Fatalf(
				"declared env keys lost %q; declared=%s",
				key, strings.Join(declared, ","),
			)
		}
	}

	// authority base_url 的 env 覆盖来自内嵌 BaseConfig，迁移后新增：它是
	// 通用段的统一键，不是 integration 自有键。
	if _, found := declaredSet["INTEGRATION_USER_ACCOUNT_SECURITY_AUTHORITY_BASE_URL"]; !found {
		t.Fatal("declared env keys must expose the shared authority base URL override")
	}
}
