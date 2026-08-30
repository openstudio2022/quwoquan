package bootstrap

import (
	"sort"
	"strings"
	"testing"
)

// 声明式 config struct 派生的 env 覆盖键必须逐一覆盖被删除的手写覆盖钩子，
// 否则部署面注入会静默失效。retiredHandwrittenKeys 是迁移前 main.go 的
// requiredEnv / positiveIntEnvOrDefault / getenvOrDefault 实际读取的键集。
//
// 无前缀的 MONGO_URI、MONGO_DATABASE、INTEGRATION_SERVICE_BASE_URL、
// USER_SERVICE_BASE_URL、REALTIME_GATEWAY_BASE_URL、REDIS_ADDR 不在其中：
// 它们是与 NOTIFICATION_ 前缀键并存的第二轨，部署面从未为本服务注入，
// 迁移时按契约单轨删除。它们同样不能进 RetiredEnvKeys——service-core 单进程
// 里 user-service、rtc-service 等模块仍在合法使用这些全局键。
func TestDeclaredEnvKeysCoverRetiredHandwrittenOverrides(t *testing.T) {
	retiredHandwrittenKeys := []string{
		"NOTIFICATION_SERVICE_ADDR",
		"NOTIFICATION_MONGO_URI",
		"NOTIFICATION_MONGO_DATABASE",
		"NOTIFICATION_INTEGRATION_BASE_URL",
		"NOTIFICATION_INTEGRATION_TIMEOUT_MS",
		"NOTIFICATION_USER_BASE_URL",
		"NOTIFICATION_REALTIME_BASE_URL",
		"NOTIFICATION_INCOMING_CALL_DEPENDENCY_TIMEOUT_MS",
		"NOTIFICATION_CLAIM_PER_SECOND",
		"NOTIFICATION_DISPATCH_PER_SECOND",
		"NOTIFICATION_RETRY_PER_SECOND",
		"NOTIFICATION_REDIS_GENERAL_DB",
		"NOTIFICATION_REDIS_REALTIME_DB",
		"NOTIFICATION_CONSUMER_NAME",
		"NOTIFICATION_USER_ACCOUNT_CLOSED_CONSUMER_NAME",
		"NOTIFICATION_RTC_CONSUMER_NAME",
		"NOTIFICATION_EXTERNAL_RESULT_CONSUMER_NAME",
		"NOTIFICATION_CHAT_OFFLINE_PUSH_ENABLED",
	}

	declaredSet := declaredEnvKeySet(t)
	for _, key := range retiredHandwrittenKeys {
		if _, found := declaredSet[key]; !found {
			t.Fatalf("declared env keys lost %q; declared=%s", key, sortedKeys(declaredSet))
		}
	}

	// authority base_url 的 env 覆盖来自内嵌 BaseConfig，迁移后新增：它是
	// 通用段的统一键，不是 notification 自有键。
	if _, found := declaredSet["NOTIFICATION_USER_ACCOUNT_SECURITY_AUTHORITY_BASE_URL"]; !found {
		t.Fatal("declared env keys must expose the shared authority base URL override")
	}
}

// 单一 NOTIFICATION_REDIS_ADDR 已被 scene 专属地址取代。它必须同时从声明键集
// 消失、并被 RetiredEnvKeys 拒收：只删读取点会让继续注入的部署静默回落 memory。
func TestRetiredRedisAddressKeyIsRejectedAndUndeclared(t *testing.T) {
	declaredSet := declaredEnvKeySet(t)
	if _, found := declaredSet["NOTIFICATION_REDIS_ADDR"]; found {
		t.Fatal("NOTIFICATION_REDIS_ADDR must not be declared after the scene split")
	}
	for _, key := range []string{
		"NOTIFICATION_REDIS_GENERAL_ADDR",
		"NOTIFICATION_REDIS_REALTIME_ADDR",
		"NOTIFICATION_REDIS_GENERAL_PASSWORD",
		"NOTIFICATION_REDIS_REALTIME_PASSWORD",
	} {
		if _, found := declaredSet[key]; !found {
			t.Fatalf("scene-scoped key %q is missing; declared=%s", key, sortedKeys(declaredSet))
		}
	}

	retired := retiredEnvKeys()
	found := false
	for _, key := range retired {
		if key == "NOTIFICATION_REDIS_ADDR" {
			found = true
		}
	}
	if !found {
		t.Fatalf("retired env keys=%v must reject NOTIFICATION_REDIS_ADDR", retired)
	}
}

func declaredEnvKeySet(t *testing.T) map[string]struct{} {
	t.Helper()
	declared, err := DeclaredEnvKeys()
	if err != nil {
		t.Fatalf("derive declared env keys: %v", err)
	}
	declaredSet := make(map[string]struct{}, len(declared))
	for _, key := range declared {
		declaredSet[key] = struct{}{}
	}
	return declaredSet
}

func sortedKeys(keys map[string]struct{}) string {
	listed := make([]string, 0, len(keys))
	for key := range keys {
		listed = append(listed, key)
	}
	sort.Strings(listed)
	return strings.Join(listed, ",")
}
