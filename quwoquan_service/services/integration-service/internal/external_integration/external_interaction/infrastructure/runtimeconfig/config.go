package runtimeconfig

import (
	"fmt"
	"net/url"
	"os"
	configrelease "quwoquan_service/runtime/configrelease"
	"strconv"
	"strings"

	"gopkg.in/yaml.v3"

	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/runtime/servicehost"
	pushapp "quwoquan_service/services/integration-service/internal/external_integration/push_delivery/application"
)

type Config struct {
	Environment string `yaml:"-"`
	Service     struct {
		Name string `yaml:"name"`
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`
	AccountSecurityAuthority AccountSecurityAuthorityConfig `yaml:"account_security_authority"`
	MongoDB                  struct {
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongodb"`
	Redis struct {
		General RedisSceneConfig `yaml:"general"`
		Rec     RedisSceneConfig `yaml:"rec"`
	} `yaml:"redis"`
	Integration struct {
		Location struct {
			NearbyDefaultRadiusMeters int     `yaml:"nearby_default_radius_meters"`
			NearbyDefaultLimit        int     `yaml:"nearby_default_limit"`
			SearchDefaultLimit        int     `yaml:"search_default_limit"`
			DefaultLatitude           float64 `yaml:"default_latitude"`
			DefaultLongitude          float64 `yaml:"default_longitude"`
		} `yaml:"location"`
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

type PublicProviderPolicyConfig struct {
	ProbePassed             bool `yaml:"probe_passed"`
	RateLimitPerSecond      int  `yaml:"rate_limit_per_second"`
	RetryMaxAttempts        int  `yaml:"retry_max_attempts"`
	RetryBackoffMs          int  `yaml:"retry_backoff_ms"`
	CircuitFailureThreshold int  `yaml:"circuit_failure_threshold"`
	CircuitResetTimeoutMs   int  `yaml:"circuit_reset_timeout_ms"`
}

type AccountSecurityAuthorityConfig struct {
	BaseURL   string `yaml:"base_url"`
	TimeoutMs int    `yaml:"timeout_ms"`
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

type RedisSceneConfig struct {
	Mode     string   `yaml:"mode"`
	Addr     string   `yaml:"addr"`
	Addrs    []string `yaml:"addrs"`
	Password string   `yaml:"password"`
	DB       int      `yaml:"db"`
	TLS      bool     `yaml:"tls"`
	Pool     struct {
		Size           int `yaml:"size"`
		MinIdle        int `yaml:"min_idle"`
		ReadTimeoutMs  int `yaml:"read_timeout_ms"`
		WriteTimeoutMs int `yaml:"write_timeout_ms"`
		DialTimeoutMs  int `yaml:"dial_timeout_ms"`
	} `yaml:"pool"`
}

func Load() (Config, error) {
	cfg := Config{}
	serviceName := strings.TrimSpace(
		servicehost.ModuleEnvironmentValue("integration-service", "SERVICE_NAME"),
	)
	if serviceName == "" {
		serviceName = "integration-service"
	}
	appEnv := getenvOrDefault("APP_ENV", "alpha")
	configRoot := strings.TrimSpace(os.Getenv("CONFIG_ROOT"))
	configVersion := strings.TrimSpace(
		servicehost.ModuleEnvironmentValue(
			"integration-service",
			"CONFIG_VERSION",
		),
	)
	if !isValidAppEnv(appEnv) {
		return Config{}, fmt.Errorf("APP_ENV must be one of alpha|beta|gamma|prod, got %q", appEnv)
	}
	cfg.Environment = appEnv
	if requiresConfigVersion(appEnv) && configVersion == "" {
		return Config{}, fmt.Errorf("CONFIG_VERSION is required when APP_ENV=%s", appEnv)
	}
	path, err := configrelease.File(configRoot, serviceName, appEnv)
	if err != nil {
		return Config{}, err
	}
	if err := MergeFile(&cfg, path); err != nil {
		return Config{}, fmt.Errorf("read generated runtime config: %w", err)
	}
	return cfg, nil
}

func isValidAppEnv(env string) bool {
	switch env {
	case "alpha", "beta", "gamma", "prod":
		return true
	default:
		return false
	}
}

func requiresConfigVersion(env string) bool {
	switch env {
	case "gamma", "prod":
		return true
	default:
		return false
	}
}

func MergeFile(cfg *Config, path string) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	if err := rejectRetiredLocationProviderConfig(raw, path); err != nil {
		return err
	}
	if err := rejectRetiredExternalInteractionConfig(raw, path); err != nil {
		return err
	}
	if err := yaml.Unmarshal(raw, cfg); err != nil {
		return fmt.Errorf("parse %s: %w", path, err)
	}
	return nil
}

func rejectRetiredLocationProviderConfig(raw []byte, path string) error {
	var document map[string]any
	if err := yaml.Unmarshal(raw, &document); err != nil {
		return fmt.Errorf("parse %s for location provider validation: %w", path, err)
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
				"%s: integration.location.%s is retired; use the generated external provider binding",
				path,
				key,
			)
		}
	}
	return nil
}

func rejectRetiredExternalInteractionConfig(raw []byte, path string) error {
	var document map[string]any
	if err := yaml.Unmarshal(raw, &document); err != nil {
		return fmt.Errorf("parse %s for external interaction validation: %w", path, err)
	}
	integration, _ := document["integration"].(map[string]any)
	externalInteraction, _ := integration["external_interaction"].(map[string]any)
	for _, key := range []string{"sms", "push"} {
		if _, found := externalInteraction[key]; found {
			return fmt.Errorf(
				"%s: integration.external_interaction.%s is retired; use the generated external provider binding",
				path,
				key,
			)
		}
	}
	return nil
}

func NormalizeDefaults(cfg *Config) {
	if strings.TrimSpace(cfg.Service.HTTP.Addr) == "" {
		cfg.Service.HTTP.Addr = ":18086"
	}
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
	if strings.TrimSpace(cfg.Redis.General.Mode) == "" {
		if cfg.Environment == "alpha" {
			cfg.Redis.General.Mode = "memory"
		} else {
			cfg.Redis.General.Mode = "standalone"
		}
	}
	if strings.TrimSpace(cfg.Redis.Rec.Mode) == "" {
		cfg.Redis.Rec.Mode = "standalone"
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
		return fmt.Errorf("mongodb.uri is required (INTEGRATION_MONGO_URI or MONGO_URI)")
	}
	if invalidRequiredConfigValue(cfg.MongoDB.Database) {
		return fmt.Errorf(
			"mongodb.database is required (INTEGRATION_MONGO_DATABASE or MONGO_DATABASE)",
		)
	}
	if invalidRequiredConfigValue(cfg.AccountSecurityAuthority.BaseURL) {
		return fmt.Errorf("account_security_authority.base_url is required")
	}
	if cfg.AccountSecurityAuthority.TimeoutMs <= 0 {
		return fmt.Errorf("account_security_authority.timeout_ms must be positive")
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

func ApplyEnvOverrides(cfg *Config) error {
	if err := rejectRetiredLocationProviderEnvOverrides(); err != nil {
		return err
	}
	if err := rejectRetiredExternalProviderEnvOverrides(); err != nil {
		return err
	}
	if value := strings.TrimSpace(os.Getenv("MONGO_URI")); value != "" {
		cfg.MongoDB.URI = value
	}
	if value := strings.TrimSpace(os.Getenv("MONGO_DATABASE")); value != "" {
		cfg.MongoDB.Database = value
	}
	if value := strings.TrimSpace(os.Getenv("INTEGRATION_MONGO_URI")); value != "" {
		cfg.MongoDB.URI = value
	}
	if value := strings.TrimSpace(os.Getenv("INTEGRATION_MONGO_DATABASE")); value != "" {
		cfg.MongoDB.Database = value
	}
	if err := applyRedisSceneEnv(
		"INTEGRATION_REDIS_GENERAL",
		&cfg.Redis.General,
	); err != nil {
		return err
	}
	if err := applyRedisSceneEnv(
		"INTEGRATION_REDIS_REC",
		&cfg.Redis.Rec,
	); err != nil {
		return err
	}
	if value := os.Getenv("INTEGRATION_SERVICE_ADDR"); value != "" {
		cfg.Service.HTTP.Addr = value
	}
	if value := os.Getenv("INTEGRATION_LOCATION_DEFAULT_LATITUDE"); value != "" {
		latitude, err := strconv.ParseFloat(value, 64)
		if err != nil {
			return fmt.Errorf("INTEGRATION_LOCATION_DEFAULT_LATITUDE must be numeric: %w", err)
		}
		cfg.Integration.Location.DefaultLatitude = latitude
	}
	if value := os.Getenv("INTEGRATION_LOCATION_DEFAULT_LONGITUDE"); value != "" {
		longitude, err := strconv.ParseFloat(value, 64)
		if err != nil {
			return fmt.Errorf("INTEGRATION_LOCATION_DEFAULT_LONGITUDE must be numeric: %w", err)
		}
		cfg.Integration.Location.DefaultLongitude = longitude
	}
	return nil
}

func applyRedisSceneEnv(prefix string, cfg *RedisSceneConfig) error {
	if value := strings.TrimSpace(os.Getenv(prefix + "_MODE")); value != "" {
		cfg.Mode = value
	}
	if value := strings.TrimSpace(os.Getenv(prefix + "_ADDR")); value != "" {
		cfg.Addr = value
	}
	if value := strings.TrimSpace(os.Getenv(prefix + "_ADDRS")); value != "" {
		cfg.Addrs = nil
		for _, raw := range strings.Split(value, ",") {
			if addr := strings.TrimSpace(raw); addr != "" {
				cfg.Addrs = append(cfg.Addrs, addr)
			}
		}
	}
	if value := strings.TrimSpace(os.Getenv(prefix + "_PASSWORD")); value != "" {
		cfg.Password = value
	}
	if value := strings.TrimSpace(os.Getenv(prefix + "_DB")); value != "" {
		parsed, err := strconv.Atoi(value)
		if err != nil || parsed < 0 {
			return fmt.Errorf("%s_DB must be a non-negative integer", prefix)
		}
		cfg.DB = parsed
	}
	if value := strings.TrimSpace(os.Getenv(prefix + "_TLS")); value != "" {
		parsed, err := strconv.ParseBool(value)
		if err != nil {
			return fmt.Errorf("%s_TLS must be boolean", prefix)
		}
		cfg.TLS = parsed
	}
	return nil
}

func rejectRetiredLocationProviderEnvOverrides() error {
	for _, key := range []string{
		"INTEGRATION_LOCATION_PROVIDER",
		"INTEGRATION_LOCATION_PRIMARY_PROVIDER",
		"INTEGRATION_LOCATION_BACKUP_PROVIDER",
		"INTEGRATION_LOCATION_TIMEOUT_MS",
	} {
		if _, found := os.LookupEnv(key); found {
			return fmt.Errorf(
				"%s is retired; use the generated external provider binding",
				key,
			)
		}
	}
	return nil
}

func rejectRetiredExternalProviderEnvOverrides() error {
	for _, key := range []string{
		"INTEGRATION_SMS_ENABLED",
		"INTEGRATION_SMS_PROVIDER",
		"INTEGRATION_SMS_TIMEOUT_MS",
		"INTEGRATION_PUSH_ENABLED",
		"INTEGRATION_PUSH_MODE",
		"INTEGRATION_PUSH_TIMEOUT_MS",
	} {
		if _, found := os.LookupEnv(key); found {
			return fmt.Errorf(
				"%s is retired; use the generated external provider binding",
				key,
			)
		}
	}
	return nil
}

func getenvOrDefault(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}
