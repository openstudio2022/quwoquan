package main

import (
	"strings"

	"quwoquan_service/runtime/controlplane"
)

func startConfigSyncLoop(
	serviceName string,
	appEnv string,
	configRoot string,
	configVersion string,
	imageVersion string,
	instanceID string,
	hotStore *controlplane.HotConfigStore,
	rateLimiter controlplane.RateLimitSetter,
) {
	baseURL := strings.TrimSpace(getenvOrDefault("PLATFORM_OPS_BASE_URL", ""))
	if baseURL == "" {
		baseURL = strings.TrimSpace(getenvOrDefault("VITE_PLATFORM_OPS_BASE_URL", ""))
	}
	if baseURL == "" {
		return
	}
	controlplane.RunConfigSyncLoop(controlplane.ConfigSyncLoopOptions{
		BaseURL:       baseURL,
		ServiceName:   serviceName,
		AppEnv:        appEnv,
		ClusterName:   defaultClusterName(appEnv),
		ConfigRoot:    configRoot,
		ConfigVersion: configVersion,
		ImageVersion:  imageVersion,
		InstanceID:    instanceID,
		HotStore:      hotStore,
		RateLimiter:   rateLimiter,
	})
}

func defaultClusterName(appEnv string) string {
	switch appEnv {
	case "beta":
		return "beta-control-a"
	case "gamma":
		return "gamma-control-a"
	case "prod":
		return "prod-control-a"
	default:
		return appEnv + "-control-a"
	}
}
