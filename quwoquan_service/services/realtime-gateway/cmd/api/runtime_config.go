package main

import (
	"fmt"

	"quwoquan_service/runtime/servicekit"
)

// config 是 realtime-gateway 的声明式配置：通用段内嵌 servicekit.BaseConfig，
// realtime scene 按「声明即装配」交给骨架（DEC-028）。
type config struct {
	servicekit.BaseConfig `yaml:",inline"`

	Redis struct {
		Realtime servicekit.RedisSceneConfig `yaml:"realtime" envPrefix:"REALTIME"`
	} `yaml:"redis" envPrefix:"REDIS"`
}

const (
	minAccountSecurityAuthorityTimeoutMs = 50
	maxAccountSecurityAuthorityTimeoutMs = 5000
)

// validateRealtimeConfig 施加网关特有的配置下界：authority 超时必须落在有界
// 区间（过小会把正常授权判定误判为不可用，过大会让握手阻塞在依赖上），
// beta/gamma/prod 不接受内存 Redis（连接租约与 presence 必须跨实例可见）。
func validateRealtimeConfig(cfg *config) error {
	timeoutMs := cfg.UserAccountSecurityAuthority.TimeoutMs
	if timeoutMs < minAccountSecurityAuthorityTimeoutMs ||
		timeoutMs > maxAccountSecurityAuthorityTimeoutMs {
		return fmt.Errorf(
			"user_account_security_authority.timeout_ms must be within [%d,%d]ms, got %d",
			minAccountSecurityAuthorityTimeoutMs,
			maxAccountSecurityAuthorityTimeoutMs,
			timeoutMs,
		)
	}
	mode, err := cfg.Redis.Realtime.DeclaredMode()
	if err != nil {
		return fmt.Errorf("redis.realtime %w", err)
	}
	if failFastEnvironment(cfg.Environment) && mode == servicekit.RedisModeMemory {
		return fmt.Errorf(
			"redis.realtime must not declare mode=%s when APP_ENV=%s",
			servicekit.RedisModeMemory, cfg.Environment,
		)
	}
	return nil
}
