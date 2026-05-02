package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
	rhttp "quwoquan_service/runtime/http"
	robs "quwoquan_service/runtime/observability"
	httpadapter "quwoquan_service/services/integration-service/internal/adapters/http"
	"quwoquan_service/services/integration-service/internal/application"
	"quwoquan_service/services/integration-service/internal/domain/location/model"
	"quwoquan_service/services/integration-service/internal/infrastructure/provider"
)

type config struct {
	Service struct {
		Name string `yaml:"name"`
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`
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
	} `yaml:"integration"`
}

func main() {
	cfg, err := loadRuntimeConfig()
	if err != nil {
		log.Fatalf("integration-service config load failed: %v", err)
	}
	applyEnvOverrides(&cfg)
	normalizeDefaults(&cfg)

	ioLogger := robs.NewIOAccessLogger(os.Stdout)
	kvFilter := robs.NewKVMetadataFilter(nil)
	processLogger, err := robs.NewProcessTraceLogger(os.Stdout, os.Stderr, robs.TraceLogLevelInfo, kvFilter)
	if err != nil {
		log.Fatalf("integration-service process logger init failed: %v", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(os.Stdout, os.Stderr, kvFilter)
	if err != nil {
		log.Fatalf("integration-service exception logger init failed: %v", err)
	}

	factoryCfg := rhttp.DefaultHTTPClientFactoryConfig()
	factoryCfg.Timeout = time.Duration(cfg.Integration.Location.TimeoutMs) * time.Millisecond
	factoryCfg.MaxRetries = 0
	factoryCfg.RetryBackoff = 0
	factoryCfg.RetryOnCodes = map[int]struct{}{}
	logCfg := rhttp.HTTPClientMiddlewareConfig{
		Service:           "integration-service",
		Origin:            "cloud",
		Direction:         "outbound",
		SourceID:          "integration-service.map-provider",
		Src:               "integration-service",
		ServiceName:       "integration-service",
		ServiceInstanceID: "local",
	}
	observedClient := rhttp.NewObservedHTTPClient(
		nil,
		factoryCfg,
		logCfg,
		ioLogger,
		processLogger,
		exceptionLogger,
	)

	clients := map[model.Provider]model.ProviderClient{
		model.ProviderBaidu: provider.NewBaiduClient(cfg.Integration.Location.BaiduBaseURL, cfg.Integration.Location.BaiduAK, observedClient),
		model.ProviderAMap:  provider.NewAMapClient(cfg.Integration.Location.AMapBaseURL, cfg.Integration.Location.AMapKey, observedClient),
	}
	locationService := application.NewService(
		cfg.Integration.Location.PrimaryProvider,
		cfg.Integration.Location.BackupProvider,
		clients,
		log.Default(),
	)
	handler := httpadapter.NewHandler(
		locationService,
		cfg.Integration.Location.NearbyDefaultRadiusMeters,
		cfg.Integration.Location.NearbyDefaultLimit,
		cfg.Integration.Location.SearchDefaultLimit,
		cfg.Integration.Location.DefaultLatitude,
		cfg.Integration.Location.DefaultLongitude,
	).Routes()

	serverCfg := rhttp.HTTPServerMiddlewareConfig{
		Service:           "integration-service",
		Origin:            "cloud",
		Direction:         "inbound",
		SourceID:          "integration-service.http",
		Src:               "gateway",
		ServiceName:       "integration-service",
		ServiceInstanceID: "local",
	}
	withObs := rhttp.NewHTTPServerMiddleware(handler, serverCfg, ioLogger, processLogger, exceptionLogger)

	server := &http.Server{
		Addr:              cfg.Service.HTTP.Addr,
		Handler:           withObs,
		ReadHeaderTimeout: 5 * time.Second,
	}
	log.Printf(
		"integration-service listening on %s primary=%s backup=%s timeout_ms=%d",
		cfg.Service.HTTP.Addr,
		cfg.Integration.Location.PrimaryProvider,
		cfg.Integration.Location.BackupProvider,
		cfg.Integration.Location.TimeoutMs,
	)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("integration-service listen and serve: %v", err)
	}
}

func loadRuntimeConfig() (config, error) {
	cfg := config{}
	serviceName := getenvOrDefault("SERVICE_NAME", "integration-service")
	appEnv := getenvOrDefault("APP_ENV", "alpha")
	configRoot := strings.TrimSpace(os.Getenv("CONFIG_ROOT"))
	configVersion := strings.TrimSpace(os.Getenv("CONFIG_VERSION"))
	if !isValidAppEnv(appEnv) {
		return config{}, fmt.Errorf("APP_ENV must be one of alpha|beta|gamma|prod-gray|prod, got %q", appEnv)
	}
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
			versionFile := filepath.Join(configRoot, "releases", "config", serviceName, configVersion+".yaml")
			if err := mergeConfigFile(&cfg, versionFile); err != nil {
				return config{}, err
			}
		}
		return cfg, nil
	}

	if err := mergeConfigFile(&cfg, filepath.Join("configs", "default", "config.yaml")); err == nil {
		_ = mergeConfigFile(&cfg, filepath.Join("configs", appEnv, "config.yaml"))
		if configVersion != "" {
			_ = mergeConfigFile(&cfg, filepath.Join("..", "..", "..", "releases", "config", serviceName, configVersion+".yaml"))
		}
		return cfg, nil
	}

	current := filepath.Join("configs", "config.yaml")
	if err := mergeConfigFile(&cfg, current); err != nil {
		return config{}, fmt.Errorf("read config failed: %w", err)
	}
	return cfg, nil
}

func isValidAppEnv(env string) bool {
	switch env {
	case "alpha", "beta", "gamma", "prod-gray", "prod":
		return true
	default:
		return false
	}
}

func requiresConfigVersion(env string) bool {
	switch env {
	case "gamma", "prod-gray", "prod":
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
	if cfg.Integration.Location.BackupProvider == "" || cfg.Integration.Location.BackupProvider == cfg.Integration.Location.PrimaryProvider {
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
}

func applyEnvOverrides(cfg *config) {
	if v := os.Getenv("INTEGRATION_SERVICE_ADDR"); v != "" {
		cfg.Service.HTTP.Addr = v
	}
	if v := os.Getenv("INTEGRATION_LOCATION_PRIMARY_PROVIDER"); v != "" {
		cfg.Integration.Location.PrimaryProvider = model.Provider(strings.ToLower(v))
	}
	if v := os.Getenv("INTEGRATION_LOCATION_BACKUP_PROVIDER"); v != "" {
		cfg.Integration.Location.BackupProvider = model.Provider(strings.ToLower(v))
	}
	if v := os.Getenv("INTEGRATION_LOCATION_TIMEOUT_MS"); v != "" {
		if ms, err := strconv.Atoi(v); err == nil && ms > 0 {
			cfg.Integration.Location.TimeoutMs = ms
		}
	}
	if v := os.Getenv("INTEGRATION_LOCATION_DEFAULT_LATITUDE"); v != "" {
		if val, err := strconv.ParseFloat(v, 64); err == nil {
			cfg.Integration.Location.DefaultLatitude = val
		}
	}
	if v := os.Getenv("INTEGRATION_LOCATION_DEFAULT_LONGITUDE"); v != "" {
		if val, err := strconv.ParseFloat(v, 64); err == nil {
			cfg.Integration.Location.DefaultLongitude = val
		}
	}
	if v := os.Getenv("INTEGRATION_LOCATION_BAIDU_AK"); v != "" {
		cfg.Integration.Location.BaiduAK = v
	}
	if v := os.Getenv("INTEGRATION_LOCATION_AMAP_KEY"); v != "" {
		cfg.Integration.Location.AMapKey = v
	}
	if v := os.Getenv("INTEGRATION_LOCATION_BAIDU_BASE_URL"); v != "" {
		cfg.Integration.Location.BaiduBaseURL = v
	}
	if v := os.Getenv("INTEGRATION_LOCATION_AMAP_BASE_URL"); v != "" {
		cfg.Integration.Location.AMapBaseURL = v
	}
}

func getenvOrDefault(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}
