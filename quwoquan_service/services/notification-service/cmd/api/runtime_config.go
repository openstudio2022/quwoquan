package bootstrap

import (
	"fmt"
	"strings"

	"gopkg.in/yaml.v3"

	"quwoquan_service/runtime/servicekit"
)

// accountSecurityReadScope 是本服务向账号安全 authority 声明的唯一 scope。
const accountSecurityReadScope = "user.account.security.read"

// config 是 notification-service 的声明式配置：通用段内嵌 servicekit.BaseConfig，
// Mongo 与两个 Redis scene 按「声明即装配」自动发现（DEC-028）。env 覆盖键由
// 服务名派生前缀 NOTIFICATION 与 envPrefix 链拼出，键名与部署面注入点逐字对齐。
type config struct {
	servicekit.BaseConfig `yaml:",inline"`

	Mongo servicekit.MongoConfig `yaml:"mongo"`

	// general 承载持久化流与投递作业，realtime 承载 incoming call 实时面；
	// 两者是 codegen message transport root 声明的必需 scene 名。
	Redis struct {
		General  servicekit.RedisSceneConfig `yaml:"general" envPrefix:"REDIS_GENERAL"`
		Realtime servicekit.RedisSceneConfig `yaml:"realtime" envPrefix:"REDIS_REALTIME"`
	} `yaml:"redis"`

	Notification struct {
		Delivery struct {
			ClaimPerSecond    int `yaml:"claim_per_second" env:"CLAIM_PER_SECOND"`
			DispatchPerSecond int `yaml:"dispatch_per_second" env:"DISPATCH_PER_SECOND"`
			RetryPerSecond    int `yaml:"retry_per_second" env:"RETRY_PER_SECOND"`
		} `yaml:"delivery"`
		Consumers struct {
			Interaction               string `yaml:"interaction" env:"CONSUMER_NAME" required:"true"`
			AccountClosure            string `yaml:"account_closure" env:"USER_ACCOUNT_CLOSED_CONSUMER_NAME" required:"true"`
			IncomingCall              string `yaml:"incoming_call" env:"RTC_CONSUMER_NAME" required:"true"`
			ExternalInteractionResult string `yaml:"external_interaction_result" env:"EXTERNAL_RESULT_CONSUMER_NAME" required:"true"`
		} `yaml:"consumers"`
		ChatOfflinePush struct {
			Enabled bool `yaml:"enabled" env:"CHAT_OFFLINE_PUSH_ENABLED"`
		} `yaml:"chat_offline_push"`
	} `yaml:"notification"`

	IntegrationService struct {
		BaseURL   string `yaml:"base_url" env:"BASE_URL" required:"true"`
		TimeoutMS int    `yaml:"timeout_ms" env:"TIMEOUT_MS"`
	} `yaml:"integration_service" envPrefix:"INTEGRATION"`

	UserService struct {
		BaseURL string `yaml:"base_url" env:"BASE_URL" required:"true"`
	} `yaml:"user_service" envPrefix:"USER"`

	RealtimeGateway struct {
		BaseURL string `yaml:"base_url" env:"BASE_URL" required:"true"`
	} `yaml:"realtime_gateway" envPrefix:"REALTIME"`

	Dependencies struct {
		TimeoutMS int `yaml:"timeout_ms" env:"TIMEOUT_MS"`
	} `yaml:"dependencies" envPrefix:"INCOMING_CALL_DEPENDENCY"`
}

// retiredEnvKeys 列出被 scene 专属键取代的环境变量键。NOTIFICATION_REDIS_ADDR
// 一旦被继续注入却无人读取，两个 scene 都会因缺地址静默回落 memory，通知流会
// 在不报错的情况下整体丢失，所以必须在启动期拒收。
func retiredEnvKeys() []string {
	return []string{"NOTIFICATION_REDIS_ADDR"}
}

// snapshotGuard 拒收仍带退役配置段的渲染快照：形状过时的快照会让新声明字段
// 全部落到零值，而零值在本服务里恰好是「可启动但不投递」的危险组合。
func snapshotGuard(raw []byte) error {
	var document map[string]any
	if err := yaml.Unmarshal(raw, &document); err != nil {
		return fmt.Errorf("parse config snapshot for retired section validation: %w", err)
	}
	if _, found := document["accountSecurityAuthority"]; found {
		return fmt.Errorf(
			"accountSecurityAuthority is retired; declare user_account_security_authority",
		)
	}
	redis, _ := document["redis"].(map[string]any)
	for _, key := range []string{"addr", "password", "general_db", "realtime_db"} {
		if _, found := redis[key]; found {
			return fmt.Errorf(
				"redis.%s is retired; declare redis.general.* and redis.realtime.* per scene",
				key,
			)
		}
	}
	return nil
}

// validateNotificationConfig 承接迁移前手写 env 读取里的领域校验：必填地址、
// 未被替换的占位符、正整数速率与非负逻辑库编号。它在骨架 required 校验之后、
// 任何观测栈与基础设施连接之前执行，所以非法配置不产生外部副作用。
func validateNotificationConfig(cfg *config) error {
	for _, endpoint := range []struct {
		name  string
		value string
	}{
		{"mongo.uri", cfg.Mongo.URI},
		{"mongo.database", cfg.Mongo.Database},
		{"integration_service.base_url", cfg.IntegrationService.BaseURL},
		{"user_service.base_url", cfg.UserService.BaseURL},
		{"realtime_gateway.base_url", cfg.RealtimeGateway.BaseURL},
		{"redis.general.addr", cfg.Redis.General.Addr},
		{"redis.realtime.addr", cfg.Redis.Realtime.Addr},
	} {
		if err := requireResolvedValue(endpoint.name, endpoint.value); err != nil {
			return err
		}
	}
	for _, rate := range []struct {
		name  string
		value int
	}{
		{"integration_service.timeout_ms", cfg.IntegrationService.TimeoutMS},
		{"dependencies.timeout_ms", cfg.Dependencies.TimeoutMS},
		{"notification.delivery.claim_per_second", cfg.Notification.Delivery.ClaimPerSecond},
		{"notification.delivery.dispatch_per_second", cfg.Notification.Delivery.DispatchPerSecond},
		{"notification.delivery.retry_per_second", cfg.Notification.Delivery.RetryPerSecond},
	} {
		if rate.value <= 0 {
			return fmt.Errorf("%s must be a positive integer, got %d", rate.name, rate.value)
		}
	}
	for _, scene := range []struct {
		name string
		db   int
	}{
		{"redis.general.db", cfg.Redis.General.DB},
		{"redis.realtime.db", cfg.Redis.Realtime.DB},
	} {
		if scene.db < 0 {
			return fmt.Errorf("%s must be a non-negative integer, got %d", scene.name, scene.db)
		}
	}
	return nil
}

// requireResolvedValue 同时拒绝空值与未被部署面替换的 ${...} 占位符：占位符
// 原样透传会让下游把字面量当成真实地址去连接，失败点远离配置来源。
func requireResolvedValue(name string, value string) error {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return fmt.Errorf("%s is required", name)
	}
	if strings.HasPrefix(trimmed, "${") && strings.HasSuffix(trimmed, "}") {
		return fmt.Errorf("%s still holds the unsubstituted placeholder %s", name, trimmed)
	}
	return nil
}
