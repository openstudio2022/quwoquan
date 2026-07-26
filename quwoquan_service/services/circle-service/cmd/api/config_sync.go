package main

import (
	"strings"

	"quwoquan_service/runtime/controlplane"
	circleconfig "quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/runtimeconfig"
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
		ClusterName:   circleconfig.DefaultClusterName(appEnv),
		ConfigRoot:    configRoot,
		ConfigVersion: configVersion,
		ImageVersion:  imageVersion,
		InstanceID:    instanceID,
		HotStore:      hotStore,
		RateLimiter:   rateLimiter,
	})
}
