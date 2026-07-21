package main

import (
	"fmt"
	"os"
	"path/filepath"
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
	if strings.TrimSpace(configRoot) != "" {
		defaultFile := filepath.Join(configRoot, "configs", serviceName, "default", "config.yaml")
		envFile := filepath.Join(configRoot, "configs", serviceName, appEnv, "config.yaml")
		if err := mergePlatformRuntimeFile(&cfg, defaultFile); err != nil {
			return platformRuntimeConfig{}, fmt.Errorf("read default config: %w", err)
		}
		if err := mergePlatformRuntimeFile(&cfg, envFile); err != nil {
			return platformRuntimeConfig{}, fmt.Errorf("read env config: %w", err)
		}
		if strings.TrimSpace(configVersion) != "" {
			versionFile := filepath.Join(configRoot, "releases", "config", serviceName, configVersion+".yaml")
			if err := mergePlatformRuntimeFile(&cfg, versionFile); err != nil {
				return platformRuntimeConfig{}, fmt.Errorf("read version config: %w", err)
			}
		}
		return cfg, nil
	}

	localDefault := filepath.Join("configs", "default", "config.yaml")
	localEnv := filepath.Join("configs", appEnv, "config.yaml")
	if _, err := os.Stat(localDefault); err == nil {
		if err := mergePlatformRuntimeFile(&cfg, localDefault); err != nil {
			return platformRuntimeConfig{}, fmt.Errorf("read local default config: %w", err)
		}
		if err := mergePlatformRuntimeFile(&cfg, localEnv); err != nil {
			return platformRuntimeConfig{}, fmt.Errorf("read local env config: %w", err)
		}
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
