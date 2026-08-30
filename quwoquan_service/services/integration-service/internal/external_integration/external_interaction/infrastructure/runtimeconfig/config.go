package runtimeconfig

import (
	"fmt"
	"net/url"
	"os"
	"strings"

	"gopkg.in/yaml.v3"

	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/runtime/servicekit"
	pushapp "quwoquan_service/services/integration-service/internal/external_integration/push_delivery/application"
)

// Config 是 integration-service 的声明式运行配置：通用段由内嵌
// servicekit.BaseConfig 单点声明，Mongo 与 Redis scene 按「声明即装配」
// 交给骨架发现，env 覆盖键由 env/envPrefix tag 派生（DEC-028）。
type Config struct {
	servicekit.BaseConfig `yaml:",inline"`

	MongoDB servicekit.MongoConfig `yaml:"mongodb"`

	Redis struct {
		General RedisSceneConfig `yaml:"general" envPrefix:"GENERAL"`
		Rec     RedisSceneConfig `yaml:"rec" envPrefix:"REC"`
	} `yaml:"redis" envPrefix:"REDIS"`

	Integration struct {
		Location struct {
			NearbyDefaultRadiusMeters int     `yaml:"nearby_default_radius_meters"`
			NearbyDefaultLimit        int     `yaml:"nearby_default_limit"`
			SearchDefaultLimit        int     `yaml:"search_default_limit"`
			DefaultLatitude           float64 `yaml:"default_latitude" env:"DEFAULT_LATITUDE"`
			DefaultLongitude          float64 `yaml:"default_longitude" env:"DEFAULT_LONGITUDE"`
		} `yaml:"location" envPrefix:"LOCATION"`
		PublicProvider struct {
			POI   PublicProviderPolicyConfig `yaml:"poi"`
			Route PublicProviderPolicyConfig `yaml:"route"`
		} `yaml:"public_provider"`
		ExternalInteraction struct {
			SMS  ExternalProviderConfig     `yaml:"sms"`
			Push PushDeliveryProviderConfig `yaml:"push"`
		} `yaml:"external_interaction"`
	} `yaml:"integration"`
}

// RedisSceneConfig 沿用 servicekit 的统一 scene 结构。
type RedisSceneConfig = servicekit.RedisSceneConfig

type PublicProviderPolicyConfig struct {
	ProbePassed             bool `yaml:"probe_passed"`
	RateLimitPerSecond      int  `yaml:"rate_limit_per_second"`
	RetryMaxAttempts        int  `yaml:"retry_max_attempts"`
	RetryBackoffMs          int  `yaml:"retry_backoff_ms"`
	CircuitFailureThreshold int  `yaml:"circuit_failure_threshold"`
	CircuitResetTimeoutMs   int  `yaml:"circuit_reset_timeout_ms"`
}

type ExternalProviderConfig struct {
	Enabled   bool   `yaml:"enabled"`
	Provider  string `yaml:"provider"`
	Endpoint  string `yaml:"endpoint"`
	Token     string `yaml:"token"`
	CAFile    string `yaml:"ca_file"`
	TimeoutMs int    `yaml:"timeout_ms"`
}

type PushDeliveryProviderConfig struct {
	Enabled            bool   `yaml:"enabled"`
	Mode               string `yaml:"mode"`
	TimeoutMs          int    `yaml:"timeout_ms"`
	Endpoint           string `yaml:"endpoint"`
	UserServiceBaseURL string `yaml:"user_service_base_url"`
	APNs               struct {
		Environment string `yaml:"environment"`
		KeyFile     string `yaml:"key_file"`
		KeyID       string `yaml:"key_id"`
		TeamID      string `yaml:"team_id"`
		Topic       string `yaml:"topic"`
	} `yaml:"apns"`
	FCM struct {
		ServiceAccountFile string `yaml:"service_account_file"`
		ProjectID          string `yaml:"project_id"`
	} `yaml:"fcm"`
}

// SnapshotGuard 拒收已退役的配置段：provider 选择与外部交互开关只能来自
// 生成的 external provider binding，出现在配置快照里即启动失败。它作为
// servicekit.BootstrapSpec.SnapshotGuard 挂接在反序列化之后。
func SnapshotGuard(raw []byte) error {
	var document map[string]any
	if err := yaml.Unmarshal(raw, &document); err != nil {
		return fmt.Errorf("parse config snapshot for retired section validation: %w", err)
	}
	integration, _ := document["integration"].(map[string]any)
	location, _ := integration["location"].(map[string]any)
	for _, key := range []string{
		"provider",
		"primary_provider",
		"backup_provider",
		"baidu_ak",
		"amap_key",
		"baidu_base_url",
		"amap_base_url",
		"timeout_ms",
	} {
		if _, found := location[key]; found {
			return fmt.Errorf(
				"integration.location.%s is retired; use the generated external provider binding",
				key,
			)
		}
	}
	externalInteraction, _ := integration["external_interaction"].(map[string]any)
	for _, key := range []string{"sms", "push"} {
		if _, found := externalInteraction[key]; found {
			return fmt.Errorf(
				"integration.external_interaction.%s is retired; use the generated external provider binding",
				key,
			)
		}
	}
	return nil
}

// RetiredEnvKeys 列出被生成的 external provider binding 取代的环境变量键。
// 任一键被注入即启动失败，交由 servicekit.RejectRetiredEnvKeys 执行。
func RetiredEnvKeys() []string {
	return []string{
		"INTEGRATION_LOCATION_PROVIDER",
		"INTEGRATION_LOCATION_PRIMARY_PROVIDER",
		"INTEGRATION_LOCATION_BACKUP_PROVIDER",
		"INTEGRATION_LOCATION_TIMEOUT_MS",
		"INTEGRATION_SMS_ENABLED",
		"INTEGRATION_SMS_PROVIDER",
		"INTEGRATION_SMS_TIMEOUT_MS",
		"INTEGRATION_PUSH_ENABLED",
		"INTEGRATION_PUSH_MODE",
		"INTEGRATION_PUSH_TIMEOUT_MS",
	}
}

// NormalizeDefaults 补齐 integration 领域策略的下界。监听地址不在此列：
// 它由配置快照与 BaseConfig 的 required 声明 fail-closed，不接受代码兜底。
func NormalizeDefaults(cfg *Config) {
	if cfg.Integration.Location.NearbyDefaultRadiusMeters <= 0 {
		cfg.Integration.Location.NearbyDefaultRadiusMeters = 3000
	}
	if cfg.Integration.Location.NearbyDefaultLimit <= 0 {
		cfg.Integration.Location.NearbyDefaultLimit = 20
	}
	if cfg.Integration.Location.SearchDefaultLimit <= 0 {
		cfg.Integration.Location.SearchDefaultLimit = 20
	}
	if cfg.Integration.Location.DefaultLatitude == 0 {
		cfg.Integration.Location.DefaultLatitude = 30.6586
	}
	if cfg.Integration.Location.DefaultLongitude == 0 {
		cfg.Integration.Location.DefaultLongitude = 104.0648
	}
	normalizePublicProviderPolicy(
		&cfg.Integration.PublicProvider.POI,
		1,
	)
	normalizePublicProviderPolicy(
		&cfg.Integration.PublicProvider.Route,
		5,
	)
	if cfg.Integration.ExternalInteraction.Push.TimeoutMs <= 0 {
		cfg.Integration.ExternalInteraction.Push.TimeoutMs = 5000
	}
}

func normalizePublicProviderPolicy(
	policy *PublicProviderPolicyConfig,
	defaultRateLimit int,
) {
	if policy.RateLimitPerSecond <= 0 {
		policy.RateLimitPerSecond = defaultRateLimit
	}
	if policy.RetryMaxAttempts <= 0 {
		policy.RetryMaxAttempts = 2
	}
	if policy.RetryBackoffMs <= 0 {
		policy.RetryBackoffMs = 200
	}
	if policy.CircuitFailureThreshold <= 0 {
		policy.CircuitFailureThreshold = 5
	}
	if policy.CircuitResetTimeoutMs <= 0 {
		policy.CircuitResetTimeoutMs = 30000
	}
}

func Validate(cfg Config) error {
	// Callers of the public config validator include contract tests and startup
	// composition. Normalize here as well as at startup so both paths enforce
	// the same fail-closed Redis policy.
	NormalizeDefaults(&cfg)
	if invalidRequiredConfigValue(cfg.MongoDB.URI) {
		return fmt.Errorf("mongodb.uri is required (INTEGRATION_MONGO_URI)")
	}
	if invalidRequiredConfigValue(cfg.MongoDB.Database) {
		return fmt.Errorf("mongodb.database is required (INTEGRATION_MONGO_DATABASE)")
	}
	if invalidRequiredConfigValue(cfg.UserAccountSecurityAuthority.BaseURL) {
		return fmt.Errorf("user_account_security_authority.base_url is required")
	}
	if cfg.UserAccountSecurityAuthority.TimeoutMs <= 0 {
		return fmt.Errorf("user_account_security_authority.timeout_ms must be positive")
	}
	for operation, providerCfg := range map[string]ExternalProviderConfig{
		reliabletask.ExternalInteractionOperationSmsOTP: cfg.Integration.ExternalInteraction.SMS,
	} {
		if !providerCfg.Enabled {
			continue
		}
		if invalidRequiredConfigValue(providerCfg.Provider) {
			return fmt.Errorf("external provider name is required for enabled operation %s", operation)
		}
		if strings.Contains(strings.ToLower(providerCfg.Provider), "mock") {
			return fmt.Errorf("enabled operation %s cannot use mock provider", operation)
		}
		if providerCfg.Provider == "ext.sms.local_capture" {
			if cfg.Environment == "prod" {
				return fmt.Errorf("SMS local_capture is forbidden in prod")
			}
		}
		if providerCfg.Provider == "ext.sms.local_capture" &&
			invalidRequiredConfigValue(providerCfg.CAFile) {
			return fmt.Errorf("SMS local_capture CA file is required")
		}
		if invalidRequiredConfigValue(providerCfg.Endpoint) {
			return fmt.Errorf("external provider endpoint is required for enabled operation %s", operation)
		}
		if invalidRequiredConfigValue(providerCfg.Token) {
			return fmt.Errorf("external provider token is required for enabled operation %s", operation)
		}
		if providerCfg.TimeoutMs <= 0 {
			return fmt.Errorf("external provider timeout is required for enabled operation %s", operation)
		}
	}
	if err := validatePushDeliveryConfig(cfg.Environment, cfg.Integration.ExternalInteraction.Push); err != nil {
		return err
	}
	return nil
}

func ValidateResultRelayRedis(environment string, cfg RedisSceneConfig) error {
	mode := strings.ToLower(strings.TrimSpace(cfg.Mode))
	if environment == "alpha" && mode == "memory" {
		return nil
	}
	switch mode {
	case "standalone":
		if invalidRequiredConfigValue(cfg.Addr) {
			return fmt.Errorf(
				"redis.general.addr is required for external result relay when APP_ENV=%s",
				environment,
			)
		}
	case "cluster":
		if len(cfg.Addrs) == 0 {
			return fmt.Errorf(
				"redis.general.addrs is required for external result relay when APP_ENV=%s",
				environment,
			)
		}
	default:
		return fmt.Errorf(
			"redis.general.mode must be memory in alpha or standalone/cluster, got %q",
			cfg.Mode,
		)
	}
	return nil
}

func validatePushDeliveryConfig(
	appEnv string,
	push PushDeliveryProviderConfig,
) error {
	if !push.Enabled {
		return nil
	}
	mode := strings.TrimSpace(push.Mode)
	if mode == "protocol_substitute" {
		if appEnv != "alpha" && appEnv != "beta" && appEnv != "gamma" {
			return fmt.Errorf(
				"integration push protocol_substitute is only permitted in alpha/beta/gamma, got APP_ENV=%s",
				appEnv,
			)
		}
		endpoint, err := url.ParseRequestURI(strings.TrimSpace(push.Endpoint))
		if err != nil || endpoint.Host == "" || endpoint.Scheme != "https" {
			return fmt.Errorf(
				"integration push protocol_substitute endpoint is invalid",
			)
		}
		if push.TimeoutMs <= 0 {
			return fmt.Errorf("integration push timeout must be positive")
		}
		return nil
	}
	if mode != "real" && mode != "remote" {
		return fmt.Errorf(
			"integration push mode must be real/remote, or protocol_substitute in alpha/beta/gamma, when APP_ENV=%s",
			appEnv,
		)
	}
	required := map[string]string{
		"user_service_base_url":    push.UserServiceBaseURL,
		"apns.environment":         push.APNs.Environment,
		"apns.key_file":            push.APNs.KeyFile,
		"apns.key_id":              push.APNs.KeyID,
		"apns.team_id":             push.APNs.TeamID,
		"apns.topic":               push.APNs.Topic,
		"fcm.service_account_file": push.FCM.ServiceAccountFile,
		"fcm.project_id":           push.FCM.ProjectID,
	}
	for field, value := range required {
		if invalidRequiredConfigValue(value) {
			return fmt.Errorf(
				"integration push %s is required when APP_ENV=%s",
				field,
				appEnv,
			)
		}
	}
	apnsEnvironment := strings.TrimSpace(push.APNs.Environment)
	if apnsEnvironment != pushapp.APNsEnvironmentSandbox &&
		apnsEnvironment != pushapp.APNsEnvironmentProduction {
		return fmt.Errorf("integration push apns.environment must be sandbox or production")
	}
	if appEnv == "prod" && apnsEnvironment != pushapp.APNsEnvironmentProduction {
		return fmt.Errorf("integration push APNs environment must be production in prod")
	}
	if push.TimeoutMs <= 0 {
		return fmt.Errorf("integration push timeout must be positive")
	}
	if err := requireReadableSecretFile("APNs key", push.APNs.KeyFile); err != nil {
		return err
	}
	if err := requireReadableSecretFile(
		"FCM service-account",
		push.FCM.ServiceAccountFile,
	); err != nil {
		return err
	}
	return nil
}

func requireReadableSecretFile(label string, path string) error {
	file, err := os.Open(strings.TrimSpace(path))
	if err != nil {
		return fmt.Errorf("integration push %s secret file is required: %w", label, err)
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil {
		return fmt.Errorf("inspect integration push %s secret file: %w", label, err)
	}
	if !info.Mode().IsRegular() || info.Size() == 0 {
		return fmt.Errorf("integration push %s secret file must be a non-empty regular file", label)
	}
	return nil
}

func invalidRequiredConfigValue(value string) bool {
	normalized := strings.TrimSpace(value)
	return normalized == "" ||
		(strings.HasPrefix(normalized, "${") && strings.HasSuffix(normalized, "}"))
}
