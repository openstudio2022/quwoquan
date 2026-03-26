package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
	rhttp "quwoquan_service/runtime/http"
	robs "quwoquan_service/runtime/observability"
	httpadapter "quwoquan_service/services/entity-service/internal/adapters/http"
	"quwoquan_service/services/entity-service/internal/application"
)

type config struct {
	Service struct {
		Name string `yaml:"name"`
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`
}

func main() {
	cfg, err := loadRuntimeConfig()
	if err != nil {
		log.Fatalf("entity-service config load failed: %v", err)
	}
	normalizeDefaults(&cfg)

	ioLogger := robs.NewIOAccessLogger(os.Stdout)
	processLogger, err := robs.NewProcessTraceLogger(os.Stdout, os.Stderr, robs.TraceLogLevelInfo, nil)
	if err != nil {
		log.Fatalf("entity-service process logger init failed: %v", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(os.Stdout, os.Stderr, nil)
	if err != nil {
		log.Fatalf("entity-service exception logger init failed: %v", err)
	}

	handler := httpadapter.NewHandler(application.NewHomepageService()).Routes()
	serverCfg := rhttp.HTTPServerMiddlewareConfig{
		Service:           "entity-service",
		Origin:            "cloud",
		Direction:         "inbound",
		SourceID:          "entity-service.http",
		Src:               "gateway",
		ServiceName:       "entity-service",
		ServiceInstanceID: hostname(),
	}
	withObs := rhttp.NewHTTPServerMiddleware(handler, serverCfg, ioLogger, processLogger, exceptionLogger)

	server := &http.Server{
		Addr:              cfg.Service.HTTP.Addr,
		Handler:           withObs,
		ReadHeaderTimeout: 5 * time.Second,
	}
	log.Printf("entity-service listening on %s", cfg.Service.HTTP.Addr)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("entity-service listen and serve: %v", err)
	}
}

func loadRuntimeConfig() (config, error) {
	cfg := config{}
	serviceName := getenvOrDefault("SERVICE_NAME", "entity-service")
	appEnv := getenvOrDefault("APP_ENV", "local")
	configRoot := strings.TrimSpace(os.Getenv("CONFIG_ROOT"))
	configVersion := strings.TrimSpace(os.Getenv("CONFIG_VERSION"))

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

	legacy := filepath.Join("configs", "config.yaml")
	if err := mergeConfigFile(&cfg, legacy); err != nil {
		return config{}, fmt.Errorf("read config failed: %w", err)
	}
	return cfg, nil
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
	if strings.TrimSpace(cfg.Service.Name) == "" {
		cfg.Service.Name = "entity-service"
	}
	if strings.TrimSpace(cfg.Service.HTTP.Addr) == "" {
		cfg.Service.HTTP.Addr = ":18084"
	}
}

func getenvOrDefault(key string, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

func hostname() string {
	name, err := os.Hostname()
	if err != nil || strings.TrimSpace(name) == "" {
		return "local"
	}
	return name
}
