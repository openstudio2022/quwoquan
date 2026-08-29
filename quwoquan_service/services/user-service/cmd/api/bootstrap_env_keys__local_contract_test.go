// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-002
package bootstrap

import (
	"reflect"
	"strings"
	"testing"

	"quwoquan_service/runtime/servicekit"
)

// TestDeclaredEnvKeysCoverRetiredHandwrittenHooks 是 DEC-028 要求的迁移等价
// 断言：声明派生的 env 覆盖键全集必须精确等于预期集合，且必须覆盖被删除的
// 手写 applyEnvOverrides 的每一个键。Postgres/Mongo/Redis 三段数据面键已按
// DEC-028 收敛为 USER_ 前缀。
func TestDeclaredEnvKeysCoverRetiredHandwrittenHooks(t *testing.T) {
	keys, err := DeclaredEnvKeys()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Postgres 连接池三项与 Redis 的 DB/TLS/ADDRS 是骨架标准覆盖面的一部分，
	// 手写钩子未覆盖它们；声明面是手写面的超集，方向安全（未注入即不生效）。
	expected := []string{
		"USER_SERVICE_ADDR",
		"USER_USER_ACCOUNT_SECURITY_AUTHORITY_BASE_URL",
		"USER_POSTGRES_DSN",
		"USER_POSTGRES_MAX_OPEN_CONNS",
		"USER_POSTGRES_MAX_IDLE_CONNS",
		"USER_POSTGRES_CONN_MAX_LIFETIME_MINUTES",
		"USER_MONGO_URI",
		"USER_MONGO_DATABASE",
		"USER_REDIS_GENERAL_MODE",
		"USER_REDIS_GENERAL_ADDR",
		"USER_REDIS_GENERAL_ADDRS",
		"USER_REDIS_GENERAL_PASSWORD",
		"USER_REDIS_GENERAL_DB",
		"USER_REDIS_GENERAL_TLS",
		"USER_REDIS_REALTIME_MODE",
		"USER_REDIS_REALTIME_ADDR",
		"USER_REDIS_REALTIME_ADDRS",
		"USER_REDIS_REALTIME_PASSWORD",
		"USER_REDIS_REALTIME_DB",
		"USER_REDIS_REALTIME_TLS",
		"INTEGRATION_EXTERNAL_INTERACTION_BASE_URL",
	}
	if !reflect.DeepEqual(keys, expected) {
		t.Fatalf("declared env keys drifted:\n got %v\nwant %v", keys, expected)
	}

	declared := make(map[string]bool, len(keys))
	for _, key := range keys {
		declared[key] = true
	}

	// 迁移前手写钩子读过的每一个键都必须在声明面留下对应消费者。左侧是迁移前
	// 键名，右侧是迁移后键名；键名相同的两项是无前缀共享契约键（envAbsolute）。
	retiredHandwrittenKeys := map[string]string{
		"USER_SERVICE_ADDR":   "USER_SERVICE_ADDR",
		"POSTGRES_DSN":        "USER_POSTGRES_DSN",
		"MONGODB_URI":         "USER_MONGO_URI",
		"MONGODB_DATABASE":    "USER_MONGO_DATABASE",
		"REDIS_ADDR":          "USER_REDIS_GENERAL_ADDR",
		"REDIS_PASSWORD":      "USER_REDIS_GENERAL_PASSWORD",
		"REDIS_REALTIME_ADDR": "USER_REDIS_REALTIME_ADDR",
		"INTEGRATION_EXTERNAL_INTERACTION_BASE_URL": "INTEGRATION_EXTERNAL_INTERACTION_BASE_URL",
	}
	for before, after := range retiredHandwrittenKeys {
		if !declared[after] {
			t.Fatalf("retired handwritten override %s lost its declaration as %s", before, after)
		}
	}

	// 无前缀数据面键已退场：service-core 把多个模块跑在同一份 os.Environ 里，
	// 共享一个无前缀存储地址键就等于静默共享一个存储实例。
	for _, unprefixed := range []string{
		"POSTGRES_DSN",
		"MONGODB_URI",
		"MONGODB_DATABASE",
		"MONGO_URI",
		"MONGO_DATABASE",
		"REDIS_ADDR",
		"REDIS_PASSWORD",
		"REDIS_REALTIME_ADDR",
	} {
		if declared[unprefixed] {
			t.Fatalf("unprefixed data-plane key %s must not be readable anymore", unprefixed)
		}
	}
}

// TestRetiredEnvKeysFailClosedOnLegacyInjection 锁定退役键的 fail-closed 语义：
// 旧注入点若漏改，服务必须启动失败，而不是让注入静默失效、带着渲染快照里的
// 旧地址起来——后者在 service-core 单进程里表现为「连到别的模块的存储」。
func TestRetiredEnvKeysFailClosedOnLegacyInjection(t *testing.T) {
	retired := retiredEnvKeys()
	if len(retired) == 0 {
		t.Fatal("retired env keys must not be empty after the prefix migration")
	}
	if err := servicekit.RejectRetiredEnvKeys(retired); err != nil {
		t.Fatalf("a clean environment must pass: %v", err)
	}
	for _, key := range retired {
		t.Run(key, func(t *testing.T) {
			t.Setenv(key, "legacy-injection")
			if err := servicekit.RejectRetiredEnvKeys(retired); err == nil ||
				!strings.Contains(err.Error(), key) {
				t.Fatalf("injecting retired key %s must fail closed, got %v", key, err)
			}
		})
	}
}

// TestRetiredEnvKeysCoverEveryUnprefixedDataPlaneKey 保证退役清单与迁移前手写
// 钩子读过的无前缀数据面键一一对应：清单漏一项，那一项的旧注入就会在迁移后
// 静默失效而没有任何运行期信号。
func TestRetiredEnvKeysCoverEveryUnprefixedDataPlaneKey(t *testing.T) {
	retired := make(map[string]bool)
	for _, key := range retiredEnvKeys() {
		retired[key] = true
	}
	for _, key := range []string{
		"POSTGRES_DSN",
		"MONGODB_URI",
		"MONGODB_DATABASE",
		"REDIS_ADDR",
		"REDIS_PASSWORD",
		"REDIS_REALTIME_ADDR",
	} {
		if !retired[key] {
			t.Fatalf("unprefixed data-plane key %s must be declared retired", key)
		}
	}
}

// TestSelfHostedAuthorityBaseURLKeyIsADetectionPortNotConfiguration 说明
// USER_USER_ACCOUNT_SECURITY_AUTHORITY_BASE_URL 的语义。该键由全仓共享的
// servicekit.BaseConfig 通用段派生，对 user-service 而言**语义不可用**：本服务
// 就是账号安全 authority 的提供方，一个指向自己入站面的 base_url 是矛盾声明，
// 会同时制造自调用与就绪自依赖。它留在声明面上不是可用配置，而是矛盾声明的
// 检测口：一旦被注入，NewAuthStack 立即 fail-closed。因此这里断言两件事——键
// 在场，且注入即启动失败。
func TestSelfHostedAuthorityBaseURLKeyIsADetectionPortNotConfiguration(t *testing.T) {
	keys, err := DeclaredEnvKeys()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	const detectionKey = "USER_USER_ACCOUNT_SECURITY_AUTHORITY_BASE_URL"
	found := false
	for _, key := range keys {
		if key == detectionKey {
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("%s must stay declared as the contradiction detection port", detectionKey)
	}

	// 该键落到 BaseConfig.UserAccountSecurityAuthority.BaseURL，骨架把它转成
	// AuthStackSpec.AccountSecurityAuthority.BaseURL。自托管声明下二者共存即拒。
	t.Setenv("AUTH_JWT_SECRET", strings.Repeat("s", 48))
	t.Setenv("AUTH_JWT_ISSUER", "quwoquan-test")
	t.Setenv("AUTH_JWT_AUDIENCE", "quwoquan-app")
	t.Setenv("AUTH_JWT_TOKEN_VERSION", "1")
	identity := servicekit.Identity{ServiceName: serviceName, AppEnv: "alpha"}

	if _, err := servicekit.NewAuthStack(identity, servicekit.AuthStackSpec{
		OperationDescriptors:               userOperationDescriptors(),
		SkipDeviceTicketAuth:               true,
		SelfHostedAccountSecurityAuthority: true,
	}); err != nil {
		t.Fatalf("self-hosted auth stack without a base URL must assemble: %v", err)
	}

	_, err = servicekit.NewAuthStack(identity, servicekit.AuthStackSpec{
		OperationDescriptors:               userOperationDescriptors(),
		SkipDeviceTicketAuth:               true,
		SelfHostedAccountSecurityAuthority: true,
		AccountSecurityAuthority: servicekit.AccountSecurityAuthoritySpec{
			BaseURL: "http://user-service:18081",
		},
	})
	if err == nil || !strings.Contains(err.Error(), "hosts the account security authority itself") {
		t.Fatalf("injecting %s must fail closed, got %v", detectionKey, err)
	}
}
