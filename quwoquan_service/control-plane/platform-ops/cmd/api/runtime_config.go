package main

import (
	"fmt"
	"os"
	configrelease "quwoquan_service/runtime/configrelease"
	"strings"

	"gopkg.in/yaml.v3"
)

type platformRuntimeConfig struct {
	Config struct {
		Version         string `yaml:"version"`
		MinImageVersion string `yaml:"min_image_version"`
		MaxImageVersion string `yaml:"max_image_version"`
	} `yaml:"config"`
	Service struct {
		Name string `yaml:"name"`
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`
	Postgres struct {
		DSN string `yaml:"dsn"`
	} `yaml:"postgres"`
}

func applyPlatformEnvOverrides(cfg *platformRuntimeConfig) {
	if dsn := strings.TrimSpace(os.Getenv("POSTGRES_DSN")); dsn != "" {
		cfg.Postgres.DSN = dsn
	}
	if strings.HasPrefix(strings.TrimSpace(cfg.Postgres.DSN), "${") {
		cfg.Postgres.DSN = ""
	}
}

func validatePlatformRuntimeConfig(cfg platformRuntimeConfig) error {
	if strings.TrimSpace(cfg.Postgres.DSN) == "" {
		return fmt.Errorf("postgres.dsn is required")
	}
	return nil
}

func resolvePlatformRuntimeIdentity() (serviceName, appEnv, configRoot, configVersion, imageVersion string) {
	serviceName = getenvOrDefault("SERVICE_NAME", "platform-ops-service")
	appEnv = getenvOrDefault("APP_ENV", "alpha")
	configRoot = strings.TrimSpace(os.Getenv("CONFIG_ROOT"))
	configVersion = strings.TrimSpace(os.Getenv("CONFIG_VERSION"))
	imageVersion = strings.TrimSpace(os.Getenv("IMAGE_VERSION"))
	return serviceName, appEnv, configRoot, configVersion, imageVersion
}

func loadPlatformRuntimeConfig(serviceName, appEnv, configRoot, configVersion string) (platformRuntimeConfig, error) {
	cfg := platformRuntimeConfig{}
	path, err := configrelease.File(configRoot, serviceName, appEnv)
	if err != nil {
		return platformRuntimeConfig{}, err
	}
	if err := mergePlatformRuntimeFile(&cfg, path); err != nil {
		return platformRuntimeConfig{}, fmt.Errorf("read generated runtime config: %w", err)
	}
	return cfg, nil
}

func mergePlatformRuntimeFile(cfg *platformRuntimeConfig, path string) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return yaml.Unmarshal(raw, cfg)
}

func getenvOrDefault(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}
