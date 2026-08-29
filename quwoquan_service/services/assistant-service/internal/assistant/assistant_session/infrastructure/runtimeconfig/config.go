package runtimeconfig

import (
	"quwoquan_service/runtime/servicekit"
)

// RedisSceneConfig 与 Mongo/Postgres 段统一使用 servicekit 的声明式类型：
// 加载、env 覆盖、连接与健康检查都由骨架按声明装配（DEC-028）。
type RedisSceneConfig = servicekit.RedisSceneConfig

type UserProfileConfig struct {
	BaseURL   string `yaml:"base_url"`
	TimeoutMs int    `yaml:"timeout_ms"`
}

// ServiceEgressConfig 是一个出向服务依赖的配置段。base_url 接受部署面覆盖
// （本地 compose 与 prod plane 都按拓扑注入），超时预算只来自渲染快照。
type ServiceEgressConfig struct {
	BaseURL   string `yaml:"base_url" env:"BASE_URL"`
	TimeoutMs int    `yaml:"timeout_ms"`
}

// ModelTierConfig 是档位到模型标识的映射。模型标识是运营可调配置，不允许写死在
// adapter 里。
type ModelTierConfig struct {
	Fast      string `yaml:"fast"`
	Balanced  string `yaml:"balanced"`
	Reasoning string `yaml:"reasoning"`
}

type ModelConfig struct {
	NativeToolCalling bool            `yaml:"native_tool_calling"`
	Tier              ModelTierConfig `yaml:"tier"`
}

// Config 是 assistant-service 的声明式运行时配置：通用段内嵌
// servicekit.BaseConfig，Mongo/Postgres/Redis 按「声明即装配」自动连接。
// env 覆盖键由服务名派生前缀 ASSISTANT 与 tag 链拼出。
type Config struct {
	servicekit.BaseConfig `yaml:",inline"`

	Postgres servicekit.PostgresConfig `yaml:"postgres"`
	MongoDB  servicekit.MongoConfig    `yaml:"mongodb"`

	Redis struct {
		Rec     RedisSceneConfig `yaml:"rec" envPrefix:"REDIS_REC"`
		General RedisSceneConfig `yaml:"general" envPrefix:"REDIS_GENERAL"`
	} `yaml:"redis"`

	Model               ModelConfig         `yaml:"model"`
	SearchService       ServiceEgressConfig `yaml:"search_service" envPrefix:"SEARCH_SERVICE"`
	EntityService       ServiceEgressConfig `yaml:"entity_service" envPrefix:"ENTITY_SERVICE"`
	ContentService      ServiceEgressConfig `yaml:"content_service" envPrefix:"CONTENT_SERVICE"`
	IntegrationService  ServiceEgressConfig `yaml:"integration_service" envPrefix:"INTEGRATION"`
	UserProfile         UserProfileConfig   `yaml:"user_profile"`
	UserService         ServiceEgressConfig `yaml:"user_service" envPrefix:"USER_SERVICE"`
	ChatService         ServiceEgressConfig `yaml:"chat_service" envPrefix:"CHAT"`
	CircleService       ServiceEgressConfig `yaml:"circle_service" envPrefix:"CIRCLE"`
	NotificationService ServiceEgressConfig `yaml:"notification_service" envPrefix:"NOTIFICATION"`
	PolicyPublication   struct {
		ReleaseArtifactRef string `yaml:"release_artifact_ref"`
		RolloutArtifactRef string `yaml:"rollout_artifact_ref"`
	} `yaml:"policy_publication"`
	SkillPackage struct {
		AssetRoot             string `yaml:"asset_root" env:"SKILL_PACKAGE_ROOT"`
		TrustedPublicKeysJSON string `yaml:"trusted_public_keys_json" env:"SKILL_PACKAGE_TRUSTED_PUBLIC_KEYS_JSON"`
	} `yaml:"skill_package"`
}
