package bootstrap

import (
	"context"
	"fmt"
	"log"
	"os"
	"strings"

	"quwoquan_service/runtime/controlplane"
	intersectionapp "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
)

// startConfigSyncLoop 接入控制面热配置通道，并把交集展示文案的运营态覆盖解析器
// 注册进 intersection application 层。
//
// 覆盖是 fail-safe 的：控制面不可达、未下发 key、值为空串时一律回落
// registry codegen 基线，交集文案不会因配置面故障而消失。
func startConfigSyncLoop(
	workers *workerRegistry,
	serviceName string,
	appEnv string,
	configRoot string,
	configVersion string,
	imageVersion string,
) error {
	hotStore := controlplane.NewHotConfigStore()
	intersectionapp.SetTextResolver(controlplane.NewIntersectionTextResolver(hotStore))

	instanceID := contentModuleEnvironmentValue("SERVICE_INSTANCE_ID", "")
	if instanceID == "" {
		hostname, err := os.Hostname()
		if err != nil {
			return fmt.Errorf("content-service config sync instance identity: %w", err)
		}
		instanceID = strings.TrimSpace(hostname)
	}

	baseURL := strings.TrimSpace(getenvOrDefault("PLATFORM_OPS_BASE_URL", ""))
	if baseURL == "" {
		if strings.EqualFold(strings.TrimSpace(appEnv), "prod") {
			return fmt.Errorf("content-service PLATFORM_OPS_BASE_URL is required in prod")
		}
		log.Printf(
			"WARN: content-service config sync disabled: PLATFORM_OPS_BASE_URL is empty (service=%s env=%s)",
			serviceName,
			appEnv,
		)
		return nil
	}

	options := controlplane.ConfigSyncLoopOptions{
		BaseURL:               baseURL,
		ServiceName:           serviceName,
		AppEnv:                appEnv,
		ClusterName:           strings.TrimSpace(getenvOrDefault("CLUSTER_NAME", "")),
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
