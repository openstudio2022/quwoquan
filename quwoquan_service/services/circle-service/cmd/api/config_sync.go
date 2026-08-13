package bootstrap

import (
	"context"
	"fmt"
	"strings"

	"quwoquan_service/runtime/controlplane"
	circleconfig "quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/runtimeconfig"
)

func registerConfigSyncWorker(
	workers *workerRegistry,
	serviceName string,
	appEnv string,
	configRoot string,
	configVersion string,
	imageVersion string,
	instanceID string,
) error {
	if workers == nil {
		return fmt.Errorf("circle-service config sync worker registry is required")
	}
	baseURL := strings.TrimSpace(getenvOrDefault("PLATFORM_OPS_BASE_URL", ""))
	if baseURL == "" {
		baseURL = strings.TrimSpace(getenvOrDefault("VITE_PLATFORM_OPS_BASE_URL", ""))
	}
	if baseURL == "" {
		if strings.EqualFold(strings.TrimSpace(appEnv), "prod") {
			return fmt.Errorf("circle-service PLATFORM_OPS_BASE_URL is required in prod (config sync/ACK loop)")
		}
		return nil
	}
	hotStore := controlplane.NewHotConfigStore()
	options := controlplane.ConfigSyncLoopOptions{
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
	}
	workers.Add(func(ctx context.Context) {
		controlplane.RunConfigSyncLoopContext(ctx, options)
	})
	return nil
}
