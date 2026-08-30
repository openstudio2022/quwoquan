// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-002
package local_contract

import (
	"reflect"
	"testing"

	bootstrap "quwoquan_service/services/content-service/cmd/api"
)

// TestDeclaredEnvKeysCoverRetiredHandwrittenHooks 是 DEC-028 要求的迁移等价
// 断言：config struct 声明派生的 env 覆盖键全集必须精确等于预期集合，且被删除
// 的手写 applyEnvOverrides 的每一个键都要有对应声明——少一个即部署面覆盖能力
// 静默丢失。
//
// 四个无前缀键随迁移改名（MONGO_URI、REPORT_DATABASE_URL、REC_MODEL_SERVICE_*、
// TAG_SERVICE_*）：单进程 service-core 内无前缀数据面键等于强制多个模块共用一个
// 实例，因此它们进入 retiredEnvKeys 并在注入时 fail-closed。
func TestDeclaredEnvKeysCoverRetiredHandwrittenHooks(t *testing.T) {
	keys, err := bootstrap.DeclaredEnvKeys()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	expected := []string{
		"CONTENT_SERVICE_ADDR",
		"CONTENT_USER_ACCOUNT_SECURITY_AUTHORITY_BASE_URL",
		"CONTENT_MONGO_URI",
		"CONTENT_MONGO_DATABASE",
		"CONTENT_POSTGRES_REPORT_DSN",
		"CONTENT_IP_LOCATION_PROVIDER",
		"CONTENT_IP_LOCATION_IPV4_DATABASE_PATH",
		"CONTENT_IP_LOCATION_IPV6_DATABASE_PATH",
		"CONTENT_IP_LOCATION_DATA_VERSION",
		"CONTENT_REDIS_REC_MODE",
		"CONTENT_REDIS_REC_ADDR",
		"CONTENT_REDIS_REC_ADDRS",
		"CONTENT_REDIS_REC_PASSWORD",
		"CONTENT_REDIS_REC_DB",
		"CONTENT_REDIS_REC_TLS",
		"CONTENT_REDIS_GENERAL_MODE",
		"CONTENT_REDIS_GENERAL_ADDR",
		"CONTENT_REDIS_GENERAL_ADDRS",
		"CONTENT_REDIS_GENERAL_PASSWORD",
		"CONTENT_REDIS_GENERAL_DB",
		"CONTENT_REDIS_GENERAL_TLS",
		"CONTENT_REDIS_REALTIME_MODE",
		"CONTENT_REDIS_REALTIME_ADDR",
		"CONTENT_REDIS_REALTIME_ADDRS",
		"CONTENT_REDIS_REALTIME_PASSWORD",
		"CONTENT_REDIS_REALTIME_DB",
		"CONTENT_REDIS_REALTIME_TLS",
		"CONTENT_REC_MODEL_SERVICE_URL",
		"CONTENT_REC_MODEL_SERVICE_TIMEOUT_MS",
		"CONTENT_REC_MODEL_SERVICE_ENABLED",
		"CONTENT_TAG_SERVICE_URL",
		"CONTENT_TAG_SERVICE_TIMEOUT_MS",
		"CONTENT_OSS_BUCKET",
		"CONTENT_OSS_REGION",
		"CONTENT_MEDIA_DELIVERY_BASE_URL",
		"CONTENT_MEDIA_UPLOAD_BASE_URL",
		"CONTENT_CDN_SIGN_KEY",
	}
	if !reflect.DeepEqual(keys, expected) {
		t.Fatalf("declared env keys drifted:\n got %v\nwant %v", keys, expected)
	}

	declared := make(map[string]bool, len(keys))
	for _, key := range keys {
		declared[key] = true
	}
	// 手写钩子的每个读取点在声明面的对应键。左边是被删除的手写键，右边是现在
	// 唯一的读取轨。
	for handwritten, replacement := range map[string]string{
		"CONTENT_SERVICE_ADDR":                   "CONTENT_SERVICE_ADDR",
		"MONGO_URI":                              "CONTENT_MONGO_URI",
		"REPORT_DATABASE_URL":                    "CONTENT_POSTGRES_REPORT_DSN",
		"REC_MODEL_SERVICE_URL":                  "CONTENT_REC_MODEL_SERVICE_URL",
		"REC_MODEL_SERVICE_ENABLED":              "CONTENT_REC_MODEL_SERVICE_ENABLED",
		"REC_MODEL_SERVICE_TIMEOUT_MS":           "CONTENT_REC_MODEL_SERVICE_TIMEOUT_MS",
		"TAG_SERVICE_URL":                        "CONTENT_TAG_SERVICE_URL",
		"TAG_SERVICE_TIMEOUT_MS":                 "CONTENT_TAG_SERVICE_TIMEOUT_MS",
		"CONTENT_IP_LOCATION_PROVIDER":           "CONTENT_IP_LOCATION_PROVIDER",
		"CONTENT_IP_LOCATION_IPV4_DATABASE_PATH": "CONTENT_IP_LOCATION_IPV4_DATABASE_PATH",
		"CONTENT_IP_LOCATION_IPV6_DATABASE_PATH": "CONTENT_IP_LOCATION_IPV6_DATABASE_PATH",
		"CONTENT_IP_LOCATION_DATA_VERSION":       "CONTENT_IP_LOCATION_DATA_VERSION",
		"CONTENT_REDIS_REC_ADDR":                 "CONTENT_REDIS_REC_ADDR",
		"CONTENT_REDIS_GENERAL_ADDR":             "CONTENT_REDIS_GENERAL_ADDR",
		"CONTENT_REDIS_REALTIME_ADDR":            "CONTENT_REDIS_REALTIME_ADDR",
		"CONTENT_OSS_BUCKET":                     "CONTENT_OSS_BUCKET",
		"CONTENT_OSS_REGION":                     "CONTENT_OSS_REGION",
		"CONTENT_MEDIA_DELIVERY_BASE_URL":        "CONTENT_MEDIA_DELIVERY_BASE_URL",
		"CONTENT_MEDIA_UPLOAD_BASE_URL":          "CONTENT_MEDIA_UPLOAD_BASE_URL",
		"CONTENT_CDN_SIGN_KEY":                   "CONTENT_CDN_SIGN_KEY",
	} {
		if !declared[replacement] {
			t.Fatalf(
				"retired handwritten override %s lost its declaration %s",
				handwritten, replacement,
			)
		}
	}
}
