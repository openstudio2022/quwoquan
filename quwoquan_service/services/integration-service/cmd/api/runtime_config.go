package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"gopkg.in/yaml.v3"

	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/integration-service/internal/domain/location/model"
	"quwoquan_service/services/integration-service/internal/infrastructure/provider"
)

type config struct {
	Environment string `yaml:"-"`
	Service     struct {
		Name string `yaml:"name"`
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`
	MongoDB struct {
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongodb"`
	Integration struct {
		Location struct {
			PrimaryProvider model.Provider `yaml:"primary_provider"`
			BackupProvider  model.Provider `yaml:"backup_provider"`
			Provider        model.Provider `yaml:"provider"`
			TimeoutMs       int            `yaml:"timeout_ms"`

			NearbyDefaultRadiusMeters int     `yaml:"nearby_default_radius_meters"`
			NearbyDefaultLimit        int     `yaml:"nearby_default_limit"`
			SearchDefaultLimit        int     `yaml:"search_default_limit"`
			DefaultLatitude           float64 `yaml:"default_latitude"`
			DefaultLongitude          float64 `yaml:"default_longitude"`

			BaiduAK      string `yaml:"baidu_ak"`
			AMapKey      string `yaml:"amap_key"`
			BaiduBaseURL string `yaml:"baidu_base_url"`
			AMapBaseURL  string `yaml:"amap_base_url"`
		} `yaml:"location"`
		ExternalInteraction struct {
			CallbackSecret string                     `yaml:"callback_secret"`
			SMS            externalProviderConfig     `yaml:"sms"`
			Push           pushDeliveryProviderConfig `yaml:"push"`
		} `yaml:"external_interaction"`
	} `yaml:"integration"`
}

type externalProviderConfig struct {
	Enabled   bool   `yaml:"enabled"`
	Provider  string `yaml:"provider"`
	Endpoint  string `yaml:"endpoint"`
	Token     string `yaml:"token"`
	TimeoutMs int    `yaml:"timeout_ms"`
}

type pushDeliveryProviderConfig struct {
	Enabled            bool   `yaml:"enabled"`
	Mode               string `yaml:"mode"`
	TimeoutMs          int    `yaml:"timeout_ms"`
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

func loadRuntimeConfig() (config, error) {
	cfg := config{}
	serviceName := getenvOrDefault("SERVICE_NAME", "integration-service")
	appEnv := getenvOrDefault("APP_ENV", "alpha")
	configRoot := strings.TrimSpace(os.Getenv("CONFIG_ROOT"))
	configVersion := strings.TrimSpace(os.Getenv("CONFIG_VERSION"))
	if !isValidAppEnv(appEnv) {
		return config{}, fmt.Errorf("APP_ENV must be one of alpha|beta|gamma|prod, got %q", appEnv)
	}
	cfg.Environment = appEnv
	if requiresConfigVersion(appEnv) && configVersion == "" {
		return config{}, fmt.Errorf("CONFIG_VERSION is required when APP_ENV=%s", appEnv)
	}

	if configRoot != "" {
		defaultFile := filepath.Join(configRoot, "configs", serviceName, "default", "config.yaml")
		envFile := filepath.Join(configRoot, "configs", serviceName, appEnv, "config.yaml")
		if err := mergeConfigFile(&cfg, defaultFile); err != nil {
			return config{}, err
		}
		if err := mergeConfigFile(&cfg, envFile); err != nil {
			return config{}, err
		}
		if configVersion != "" {
			versionFile := filepath.Join(
				configRoot,
				"quwoquan_service",
				"services",
				serviceName,
				"configs",
				"releases",
				configVersion+".yaml",
			)
			if err := mergeConfigFile(&cfg, versionFile); err != nil {
				return config{}, err
			}
		}
		return cfg, nil
	}

	defaultPath := filepath.Join("configs", "default", "config.yaml")
	if err := mergeConfigFile(&cfg, defaultPath); err != nil {
		return config{}, err
	}
	if err := mergeConfigFile(&cfg, filepath.Join("configs", appEnv, "config.yaml")); err != nil {
		return config{}, err
	}
	if configVersion != "" {
		if err := mergeConfigFile(
			&cfg,
			filepath.Join("configs", "releases", configVersion+".yaml"),
		); err != nil {
			return config{}, err
		}
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

func mergeConfigFile(cfg *config, path string) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	if err := yaml.Unmarshal(raw, cfg); err != nil {
		return fmt.Errorf("parse %s: %w", path, err)
	}
	return nil
}

func normalizeDefaults(cfg *config) {
	if strings.TrimSpace(cfg.Service.HTTP.Addr) == "" {
		cfg.Service.HTTP.Addr = ":18086"
	}
	if cfg.Integration.Location.TimeoutMs <= 0 {
		cfg.Integration.Location.TimeoutMs = 1200
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
	if cfg.Integration.Location.PrimaryProvider == "" {
		if cfg.Integration.Location.Provider != "" {
			cfg.Integration.Location.PrimaryProvider = cfg.Integration.Location.Provider
		} else {
			cfg.Integration.Location.PrimaryProvider = model.ProviderBaidu
		}
	}
	if cfg.Integration.Location.BackupProvider == "" ||
		cfg.Integration.Location.BackupProvider == cfg.Integration.Location.PrimaryProvider {
		if cfg.Integration.Location.PrimaryProvider == model.ProviderBaidu {
			cfg.Integration.Location.BackupProvider = model.ProviderAMap
		} else {
			cfg.Integration.Location.BackupProvider = model.ProviderBaidu
		}
	}
	if cfg.Integration.Location.BaiduBaseURL == "" {
		cfg.Integration.Location.BaiduBaseURL = "https://api.map.baidu.com"
	}
	if cfg.Integration.Location.AMapBaseURL == "" {
		cfg.Integration.Location.AMapBaseURL = "https://restapi.amap.com"
	}
	if cfg.Integration.ExternalInteraction.Push.TimeoutMs <= 0 {
		cfg.Integration.ExternalInteraction.Push.TimeoutMs = 5000
	}
}

func validateRuntimeConfig(cfg config) error {
	if invalidRequiredConfigValue(cfg.MongoDB.URI) {
		return fmt.Errorf("mongodb.uri is required (INTEGRATION_MONGO_URI or MONGO_URI)")
	}
	if invalidRequiredConfigValue(cfg.MongoDB.Database) {
		return fmt.Errorf(
			"mongodb.database is required (INTEGRATION_MONGO_DATABASE or MONGO_DATABASE)",
		)
	}
	for operation, providerCfg := range map[string]externalProviderConfig{
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

func validatePushDeliveryConfig(
	appEnv string,
	push pushDeliveryProviderConfig,
) error {
	if !push.Enabled {
		return nil
	}
	mode := strings.TrimSpace(push.Mode)
	if appEnv == "alpha" {
		if mode != "fake" {
			return fmt.Errorf("integration push mode must be fake when APP_ENV=alpha")
		}
		if push.TimeoutMs <= 0 {
			return fmt.Errorf("integration push timeout must be positive")
		}
		return nil
	}
	if mode != "real" {
		return fmt.Errorf(
			"integration push mode must be real when APP_ENV=%s",
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
	if apnsEnvironment != provider.APNsEnvironmentSandbox &&
		apnsEnvironment != provider.APNsEnvironmentProduction {
		return fmt.Errorf("integration push apns.environment must be sandbox or production")
	}
	if appEnv == "prod" && apnsEnvironment != provider.APNsEnvironmentProduction {
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

func applyEnvOverrides(cfg *config) error {
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
	if value := os.Getenv("INTEGRATION_SERVICE_ADDR"); value != "" {
		cfg.Service.HTTP.Addr = value
	}
	if value := os.Getenv("INTEGRATION_LOCATION_PRIMARY_PROVIDER"); value != "" {
		cfg.Integration.Location.PrimaryProvider = model.Provider(strings.ToLower(value))
	}
	if value := os.Getenv("INTEGRATION_LOCATION_BACKUP_PROVIDER"); value != "" {
		cfg.Integration.Location.BackupProvider = model.Provider(strings.ToLower(value))
	}
	if value := os.Getenv("INTEGRATION_LOCATION_TIMEOUT_MS"); value != "" {
		timeoutMs, err := parsePositiveIntEnv("INTEGRATION_LOCATION_TIMEOUT_MS", value)
		if err != nil {
			return err
		}
		cfg.Integration.Location.TimeoutMs = timeoutMs
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
	if value := os.Getenv("INTEGRATION_LOCATION_BAIDU_AK"); value != "" {
		cfg.Integration.Location.BaiduAK = value
	}
	if value := os.Getenv("INTEGRATION_LOCATION_AMAP_KEY"); value != "" {
		cfg.Integration.Location.AMapKey = value
	}
	if value := os.Getenv("INTEGRATION_LOCATION_BAIDU_BASE_URL"); value != "" {
		cfg.Integration.Location.BaiduBaseURL = value
	}
	if value := os.Getenv("INTEGRATION_LOCATION_AMAP_BASE_URL"); value != "" {
		cfg.Integration.Location.AMapBaseURL = value
	}
	if err := applyExternalProviderEnv(
		&cfg.Integration.ExternalInteraction.SMS,
		"INTEGRATION_SMS",
	); err != nil {
		return err
	}
	if err := applyPushDeliveryEnv(
		&cfg.Integration.ExternalInteraction.Push,
	); err != nil {
		return err
	}
	if value := strings.TrimSpace(os.Getenv("INTEGRATION_CALLBACK_SECRET")); value != "" {
		cfg.Integration.ExternalInteraction.CallbackSecret = value
	}
	return nil
}

func applyExternalProviderEnv(cfg *externalProviderConfig, prefix string) error {
	if raw, present := os.LookupEnv(prefix + "_ENABLED"); present {
		value, err := strconv.ParseBool(strings.TrimSpace(raw))
		if err != nil {
			return fmt.Errorf("%s_ENABLED must be boolean: %w", prefix, err)
		}
		cfg.Enabled = value
	}
	if value := strings.TrimSpace(os.Getenv(prefix + "_PROVIDER")); value != "" {
		cfg.Provider = value
	}
	if value := strings.TrimSpace(os.Getenv(prefix + "_ENDPOINT")); value != "" {
		cfg.Endpoint = value
	}
	if value := strings.TrimSpace(os.Getenv(prefix + "_TOKEN")); value != "" {
		cfg.Token = value
	}
	if raw := strings.TrimSpace(os.Getenv(prefix + "_TIMEOUT_MS")); raw != "" {
		value, err := parsePositiveIntEnv(prefix+"_TIMEOUT_MS", raw)
		if err != nil {
			return err
		}
		cfg.TimeoutMs = value
	}
	return nil
}

func applyPushDeliveryEnv(cfg *pushDeliveryProviderConfig) error {
	if raw, present := os.LookupEnv("INTEGRATION_PUSH_ENABLED"); present {
		value, err := strconv.ParseBool(strings.TrimSpace(raw))
		if err != nil {
			return fmt.Errorf("INTEGRATION_PUSH_ENABLED must be boolean: %w", err)
		}
		cfg.Enabled = value
	}
	if value := strings.TrimSpace(os.Getenv("INTEGRATION_PUSH_MODE")); value != "" {
		cfg.Mode = value
	}
	if raw := strings.TrimSpace(os.Getenv("INTEGRATION_PUSH_TIMEOUT_MS")); raw != "" {
		value, err := parsePositiveIntEnv("INTEGRATION_PUSH_TIMEOUT_MS", raw)
		if err != nil {
			return err
		}
		cfg.TimeoutMs = value
	}
	if value := strings.TrimSpace(os.Getenv("INTEGRATION_PUSH_USER_SERVICE_BASE_URL")); value != "" {
		cfg.UserServiceBaseURL = value
	}
	if value := strings.TrimSpace(os.Getenv("INTEGRATION_PUSH_APNS_ENVIRONMENT")); value != "" {
		cfg.APNs.Environment = value
	}
	if value := strings.TrimSpace(os.Getenv("INTEGRATION_PUSH_APNS_KEY_FILE")); value != "" {
		cfg.APNs.KeyFile = value
	}
	if value := strings.TrimSpace(os.Getenv("INTEGRATION_PUSH_APNS_KEY_ID")); value != "" {
		cfg.APNs.KeyID = value
	}
	if value := strings.TrimSpace(os.Getenv("INTEGRATION_PUSH_APNS_TEAM_ID")); value != "" {
		cfg.APNs.TeamID = value
	}
	if value := strings.TrimSpace(os.Getenv("INTEGRATION_PUSH_APNS_TOPIC")); value != "" {
		cfg.APNs.Topic = value
	}
	if value := strings.TrimSpace(os.Getenv("INTEGRATION_PUSH_FCM_SERVICE_ACCOUNT_FILE")); value != "" {
		cfg.FCM.ServiceAccountFile = value
	}
	if value := strings.TrimSpace(os.Getenv("INTEGRATION_PUSH_FCM_PROJECT_ID")); value != "" {
		cfg.FCM.ProjectID = value
	}
	return nil
}

func parsePositiveIntEnv(key string, raw string) (int, error) {
	value, err := strconv.Atoi(strings.TrimSpace(raw))
	if err != nil || value <= 0 {
		return 0, fmt.Errorf("%s must be a positive integer", key)
	}
	return value, nil
}

func getenvOrDefault(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}
