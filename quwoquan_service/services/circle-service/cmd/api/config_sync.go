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
) {
	baseURL := strings.TrimSpace(getenvOrDefault("PLATFORM_OPS_BASE_URL", ""))
	if baseURL == "" {
		baseURL = strings.TrimSpace(getenvOrDefault("VITE_PLATFORM_OPS_BASE_URL", ""))
	}
	if baseURL == "" {
		if strings.EqualFold(strings.TrimSpace(appEnv), "prod") {
			panic("circle-service PLATFORM_OPS_BASE_URL is required in prod (config sync/ACK loop)")
		}
		return
	}
	controlplane.RunConfigSyncLoop(controlplane.ConfigSyncLoopOptions{
		BaseURL:               baseURL,
		ServiceName:           serviceName,
		AppEnv:                appEnv,
		ClusterName:           circleconfig.DefaultClusterName(appEnv),
		ConfigRoot:            configRoot,
		ConfigVersion:         configVersion,
		ImageVersion:          imageVersion,
		ReleaseManifestDigest: strings.TrimSpace(getenvOrDefault("RELEASE_MANIFEST_DIGEST", "")),
		InstanceID:            instanceID,
		HotStore:              hotStore,
	})
}
