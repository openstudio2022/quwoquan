package main

import (
	"testing"
)

// TestDeclaredEnvKeysCoverStandardizedDeploymentContract 锁定声明式配置派生的
// env 覆盖键集：realtime-gateway 迁移到 servicekit.Bootstrap 时把手写的
// REALTIME_REDIS_* / REALTIME_GATEWAY_ADDR 统一到 <SERVICE>_<PATH> 标准形态，
// 部署面（compose、prod plane 渲染）已同步。此断言防止键集再次漂移。
func TestDeclaredEnvKeysCoverStandardizedDeploymentContract(t *testing.T) {
	keys, err := DeclaredEnvKeys()
	if err != nil {
		t.Fatalf("declared env keys: %v", err)
	}
	declared := map[string]bool{}
	for _, key := range keys {
		declared[key] = true
	}
	for _, required := range []string{
		"REALTIME_GATEWAY_SERVICE_ADDR",
		"REALTIME_GATEWAY_USER_ACCOUNT_SECURITY_AUTHORITY_BASE_URL",
		"REALTIME_GATEWAY_REDIS_REALTIME_MODE",
		"REALTIME_GATEWAY_REDIS_REALTIME_ADDR",
		"REALTIME_GATEWAY_REDIS_REALTIME_ADDRS",
		"REALTIME_GATEWAY_REDIS_REALTIME_PASSWORD",
	} {
		if !declared[required] {
			t.Fatalf("declared env keys missing %s; got %v", required, keys)
		}
	}
	// 迁移前的手写覆盖键必须彻底退役：保留它们会形成第二套注入真相源。
	for _, retired := range []string{
		"REALTIME_REDIS_MODE",
		"REALTIME_REDIS_ADDR",
		"REALTIME_REDIS_ADDRS",
		"REALTIME_REDIS_PASSWORD",
		"REALTIME_GATEWAY_ADDR",
	} {
		if declared[retired] {
			t.Fatalf("retired env key %s is still declared", retired)
		}
	}
}

// TestValidateRealtimeConfigRejectsMemoryRedisOutsideAlpha 锁定网关的 fail-closed
// 环境分档：连接租约与 presence 必须跨实例可见。
func TestValidateRealtimeConfigRejectsMemoryRedisOutsideAlpha(t *testing.T) {
	cfg := &config{}
	cfg.Environment = "gamma"
	cfg.UserAccountSecurityAuthority.TimeoutMs = 500
	cfg.Redis.Realtime.Mode = "memory"
	if err := validateRealtimeConfig(cfg); err == nil {
		t.Fatalf("expected memory redis rejection in gamma")
	}

	cfg.Environment = "alpha"
	if err := validateRealtimeConfig(cfg); err != nil {
		t.Fatalf("alpha must accept memory redis: %v", err)
	}
}

// TestValidateRealtimeConfigBoundsAuthorityTimeout 锁定 authority 超时的有界
// 区间：过小会把正常授权判定误判为不可用，过大会让握手阻塞在依赖上。
func TestValidateRealtimeConfigBoundsAuthorityTimeout(t *testing.T) {
	for _, timeoutMs := range []int{0, 49, 5001} {
		cfg := &config{}
		cfg.Environment = "alpha"
		cfg.UserAccountSecurityAuthority.TimeoutMs = timeoutMs
		cfg.Redis.Realtime.Mode = "memory"
		if err := validateRealtimeConfig(cfg); err == nil {
			t.Fatalf("expected rejection for timeout_ms=%d", timeoutMs)
		}
	}
}
