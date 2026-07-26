package main

import (
	"fmt"
	"os"
	configrelease "quwoquan_service/runtime/configrelease"
	"strconv"

	"gopkg.in/yaml.v3"
)

type notificationRuntimeConfig struct {
	Service struct {
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`
	AccountSecurityAuthority struct {
		BaseURL   string `yaml:"baseUrl"`
		TimeoutMS int    `yaml:"timeoutMs"`
	} `yaml:"accountSecurityAuthority"`
	Notification struct {
		Delivery struct {
			ClaimPerSecond    int `yaml:"claim_per_second"`
			DispatchPerSecond int `yaml:"dispatch_per_second"`
			RetryPerSecond    int `yaml:"retry_per_second"`
		} `yaml:"delivery"`
		Consumers struct {
			Interaction               string `yaml:"interaction"`
			AccountClosure            string `yaml:"account_closure"`
			IncomingCall              string `yaml:"incoming_call"`
			ExternalInteractionResult string `yaml:"external_interaction_result"`
		} `yaml:"consumers"`
	} `yaml:"notification"`
	Mongo struct {
		Database string `yaml:"database"`
	} `yaml:"mongo"`
	IntegrationService struct {
		BaseURL   string `yaml:"base_url"`
		TimeoutMS int    `yaml:"timeout_ms"`
	} `yaml:"integration_service"`
	UserService struct {
		BaseURL string `yaml:"base_url"`
	} `yaml:"user_service"`
	RealtimeGateway struct {
		BaseURL string `yaml:"base_url"`
	} `yaml:"realtime_gateway"`
	Dependencies struct {
		TimeoutMS int `yaml:"timeout_ms"`
	} `yaml:"dependencies"`
	Redis struct {
		Addr       string `yaml:"addr"`
		GeneralDB  int    `yaml:"general_db"`
		RealtimeDB int    `yaml:"realtime_db"`
	} `yaml:"redis"`
}

func loadNotificationRuntimeConfig(serviceName, environment, configRoot string) (notificationRuntimeConfig, error) {
	path, err := configrelease.File(configRoot, serviceName, environment)
	if err != nil {
		return notificationRuntimeConfig{}, err
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return notificationRuntimeConfig{}, err
	}
	var cfg notificationRuntimeConfig
	if err := yaml.Unmarshal(raw, &cfg); err != nil {
		return notificationRuntimeConfig{}, fmt.Errorf("parse %s: %w", path, err)
	}
	return cfg, nil
}

func applyNotificationRuntimeConfig(cfg notificationRuntimeConfig) error {
	values := map[string]string{
		"NOTIFICATION_SERVICE_ADDR":                        cfg.Service.HTTP.Addr,
		"NOTIFICATION_MONGO_DATABASE":                      cfg.Mongo.Database,
		"NOTIFICATION_INTEGRATION_BASE_URL":                cfg.IntegrationService.BaseURL,
		"NOTIFICATION_INTEGRATION_TIMEOUT_MS":              strconv.Itoa(cfg.IntegrationService.TimeoutMS),
		"NOTIFICATION_USER_BASE_URL":                       cfg.UserService.BaseURL,
		"NOTIFICATION_REALTIME_BASE_URL":                   cfg.RealtimeGateway.BaseURL,
		"NOTIFICATION_INCOMING_CALL_DEPENDENCY_TIMEOUT_MS": strconv.Itoa(cfg.Dependencies.TimeoutMS),
		"NOTIFICATION_CLAIM_PER_SECOND":                    strconv.Itoa(cfg.Notification.Delivery.ClaimPerSecond),
		"NOTIFICATION_DISPATCH_PER_SECOND":                 strconv.Itoa(cfg.Notification.Delivery.DispatchPerSecond),
		"NOTIFICATION_RETRY_PER_SECOND":                    strconv.Itoa(cfg.Notification.Delivery.RetryPerSecond),
		"NOTIFICATION_REDIS_ADDR":                          cfg.Redis.Addr,
		"NOTIFICATION_REDIS_GENERAL_DB":                    strconv.Itoa(cfg.Redis.GeneralDB),
		"NOTIFICATION_REDIS_REALTIME_DB":                   strconv.Itoa(cfg.Redis.RealtimeDB),
		"NOTIFICATION_CONSUMER_NAME":                       cfg.Notification.Consumers.Interaction,
		"NOTIFICATION_USER_ACCOUNT_CLOSED_CONSUMER_NAME":   cfg.Notification.Consumers.AccountClosure,
		"NOTIFICATION_RTC_CONSUMER_NAME":                   cfg.Notification.Consumers.IncomingCall,
		"NOTIFICATION_EXTERNAL_RESULT_CONSUMER_NAME":       cfg.Notification.Consumers.ExternalInteractionResult,
	}
	for key, value := range values {
		if os.Getenv(key) != "" || value == "" {
			continue
		}
		if err := os.Setenv(key, value); err != nil {
			return err
		}
	}
	return nil
}
