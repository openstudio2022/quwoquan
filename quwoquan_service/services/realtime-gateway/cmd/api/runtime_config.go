package main

import (
	"fmt"
	"os"
	"strings"

	configrelease "quwoquan_service/runtime/configrelease"

	"gopkg.in/yaml.v3"
)

type realtimeRuntimeConfig struct {
	Service struct {
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`
	Redis struct {
		Realtime struct {
			Mode  string   `yaml:"mode"`
			Addr  string   `yaml:"addr"`
			Addrs []string `yaml:"addrs"`
		} `yaml:"realtime"`
	} `yaml:"redis"`
	UserService struct {
		AccountSecurity struct {
			BaseURL   string `yaml:"base_url"`
			TimeoutMs int    `yaml:"timeout_ms"`
		} `yaml:"account_security"`
	} `yaml:"user_service"`
}

const (
	minAccountSecurityAuthorityTimeoutMs = 50
	maxAccountSecurityAuthorityTimeoutMs = 5000
)

func loadRealtimeRuntimeConfig(serviceName, environment, configRoot string) (realtimeRuntimeConfig, error) {
	path, err := configrelease.File(configRoot, serviceName, environment)
	if err != nil {
		return realtimeRuntimeConfig{}, err
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return realtimeRuntimeConfig{}, err
	}
	var cfg realtimeRuntimeConfig
	if err := yaml.Unmarshal(raw, &cfg); err != nil {
		return realtimeRuntimeConfig{}, fmt.Errorf("parse %s: %w", path, err)
	}
	cfg.Service.HTTP.Addr = strings.TrimSpace(cfg.Service.HTTP.Addr)
	cfg.Redis.Realtime.Mode = strings.TrimSpace(cfg.Redis.Realtime.Mode)
	cfg.Redis.Realtime.Addr = strings.TrimSpace(cfg.Redis.Realtime.Addr)
	cfg.UserService.AccountSecurity.BaseURL = strings.TrimSpace(
		cfg.UserService.AccountSecurity.BaseURL,
	)
	if cfg.Service.HTTP.Addr == "" || cfg.Redis.Realtime.Mode == "" ||
		cfg.UserService.AccountSecurity.BaseURL == "" ||
		cfg.UserService.AccountSecurity.TimeoutMs <
			minAccountSecurityAuthorityTimeoutMs ||
		cfg.UserService.AccountSecurity.TimeoutMs >
			maxAccountSecurityAuthorityTimeoutMs {
		return realtimeRuntimeConfig{}, fmt.Errorf(
			"service.http.addr, redis.realtime.mode and bounded user_service.account_security config are required",
		)
	}
	return cfg, nil
}
