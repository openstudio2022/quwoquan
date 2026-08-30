package bootstrap

import (
	"testing"

	"quwoquan_service/runtime/servicekit"
)

// TestRetiredUnscopedRedisKeysFailClosed 锁定 scene 专属键改名的两端：不带 scene
// 段的旧键必须从声明面消失并在启动期被拒收，带 scene 段的新键必须在声明面。
//
// 只删读取点不够——继续注入旧键的部署面会静默失去地址，general scene 于是缺地址
// 而在装配期判否，报出的却是「缺地址」而不是「你注入的键名已经没有读取点」。
// `<PREFIX>_REDIS_ADDR` 这个形状在本仓库还被 rtc-service 用作跨 scene 共享地址位，
// 所以旧键留在声明面不只是冗余，它让同一形状承载两种语义。
func TestRetiredUnscopedRedisKeysFailClosed(t *testing.T) {
	keys, err := DeclaredEnvKeys()
	if err != nil {
		t.Fatalf("derive declared env keys: %v", err)
	}
	declared := make(map[string]bool, len(keys))
	for _, key := range keys {
		declared[key] = true
	}
	for _, key := range []string{
		"CIRCLE_REDIS_GENERAL_ADDR",
		"CIRCLE_REDIS_GENERAL_PASSWORD",
	} {
		if !declared[key] {
			t.Fatalf("scene-scoped key %s is missing from %v", key, keys)
		}
	}

	retired := retiredEnvKeys()
	for _, key := range retired {
		if declared[key] {
			t.Fatalf("%s is retired but still declared as an override key", key)
		}
	}
	if err := servicekit.RejectRetiredEnvKeys(retired); err != nil {
		t.Fatalf("a clean process environment must pass: %v", err)
	}
	t.Setenv("CIRCLE_REDIS_ADDR", "redis:6379")
	if err := servicekit.RejectRetiredEnvKeys(retired); err == nil {
		t.Fatal("legacy CIRCLE_REDIS_ADDR injection must fail closed")
	}
}
