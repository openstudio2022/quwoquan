package bootstrap

import (
	"net/http"
	"os"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/servicehost"
	"quwoquan_service/runtime/servicekit"
)

const serviceName = "user-service"

// accountSecurityHealthPath 是 rtauth.HTTPAccountSecurityAuthority 的就绪探测
// 端点，由 account_lifecycle_handler 注册。它必须在 admission 之前放行，
// 见 NewModule 里 PreAdmissionPaths 的论证。
const accountSecurityHealthPath = "/internal/user/account-security/health"

// userOperationDescriptors 是 user 域 operation 预算的唯一来源，装配层的路由
// 守卫与传输层上限都从它派生。
func userOperationDescriptors() []rtauth.OperationSecurityDescriptor {
	return operationsecurity.ForDomain("user")
}

// DeclaredEnvKeys 暴露声明派生的 env 覆盖键全集，供等价断言测试锁定键集不随
// 重构漂移。
func DeclaredEnvKeys() ([]string, error) {
	return servicekit.EnvOverrideKeys(servicekit.DefaultEnvPrefix(serviceName), &config{})
}

// retiredEnvKeys 是迁移前手写 applyEnvOverrides 读过的无前缀数据面键。
// service-core 把 11 个模块跑在同一份 os.Environ 里，无前缀的存储地址键一旦
// 被两个模块读到就等于共享一个存储实例，且这种耦合不出现在任何配置文件里
// （DEC-028）。任一键仍被注入即启动失败，而不是让旧注入静默失效、服务带着
// 渲染快照里的旧地址起来。
func retiredEnvKeys() []string {
	return []string{
		"POSTGRES_DSN",
		"MONGODB_URI",
		"MONGODB_DATABASE",
		"REDIS_ADDR",
		"REDIS_PASSWORD",
		"REDIS_REALTIME_ADDR",
	}
}

// newUserOperationGuard 沿用 runtime 身份感知的 operation 边界：验证通过的
// mutable test-live 组合放行 blocked operation 以产生 readiness 证据，
// immutable release 组合保持 public boundary fail-closed。
func newUserOperationGuard(
	identity servicekit.Identity,
) (func(http.Handler) http.Handler, error) {
	return rtauth.EnforceOperationAuthorizationForRuntime(
		userOperationDescriptors(),
		identity.AppEnv,
		servicehost.RuntimeIdentityEnvironment(),
	)
}

// config 是 user-service 的声明式运行配置（DEC-028）：通用段内嵌
// servicekit.BaseConfig，env 覆盖键由服务名派生的前缀 USER 与字段 tag 拼出，
// 手写的 applyEnvOverrides 由声明面取代。Postgres 按「声明即装配」自动发现。
type config struct {
	servicekit.BaseConfig `yaml:",inline"`

	Postgres servicekit.PostgresConfig `yaml:"postgres"`

	// MongoDB 不用 servicekit.MongoConfig：那份声明把 uri/database 标为
	// required，会把 user-service 现有的「未注入 uri 即 8 处功能降级」变成
	// 「未注入即拒绝启动」。这份隐性可选依赖由 OPEN-009 承接收敛，收敛前
	// 保持等价，因此这里自带一份不带 required 的声明。
	MongoDB struct {
		URI      string `yaml:"uri" env:"MONGO_URI"`
		Database string `yaml:"database" env:"MONGO_DATABASE"`
	} `yaml:"mongodb"`

	Redis struct {
		General  servicekit.RedisSceneConfig `yaml:"general" envPrefix:"REDIS_GENERAL"`
		Realtime servicekit.RedisSceneConfig `yaml:"realtime" envPrefix:"REDIS_REALTIME"`
	} `yaml:"redis"`

	Integration struct {
		// 被调服务地址对多个调用方是同一个值，部署面按无前缀共享键注入，
		// 因此用 envAbsolute 而非服务前缀派生。
		ExternalInteractionBaseURL string `yaml:"external_interaction_base_url" envAbsolute:"INTEGRATION_EXTERNAL_INTERACTION_BASE_URL"`
	} `yaml:"integration"`

	ResearchIdentity struct {
		Enabled    bool `yaml:"enabled"`
		TTLSeconds int  `yaml:"ttl_seconds"`
	} `yaml:"research_identity"`
}

// resolveRedisScenes 装配三个 codegen scene 名。配置 schema 只声明 redis.general
// 段，realtime 在任何环境的渲染快照里都缺席，因此本服务显式声明「realtime 整段
// 缺席时复用 general 的声明」——用户域实时同步流与读路径落在同一个实例上。
//
// 复用的是完整一段，不做字段级回落：把 realtime 的 mode 和 general 的地址拼在
// 一起会得到一份没人声明过的配置，出问题时没有任何一个文件能解释生效值。
// USER_REDIS_REALTIME_* 因此是「整段独立声明」的入口：注入其中任何一项就必须把
// 这个 scene 声明完整。
func resolveRedisScenes(cfg *config) map[string]servicekit.RedisSceneConfig {
	general := cfg.Redis.General
	realtime := cfg.Redis.Realtime
	if realtime.IsUndeclared() {
		realtime = general
	}
	return map[string]servicekit.RedisSceneConfig{
		"general":  general,
		"realtime": realtime,
		"rec":      general,
	}
}

func getenvOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
