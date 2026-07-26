package main

import (
	"log"
	"os"
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
) {
	baseURL := strings.TrimSpace(os.Getenv("PLATFORM_OPS_BASE_URL"))
	if baseURL == "" {
		baseURL = strings.TrimSpace(os.Getenv("VITE_PLATFORM_OPS_BASE_URL"))
	}
	if baseURL == "" {
		// 生产缺失时必须 fail-fast；beta/gamma 明确记录禁用状态，
		// 不得伪装已有配置 ACK。
		if strings.EqualFold(strings.TrimSpace(appEnv), "prod") {
			log.Fatal("product-ops-service PLATFORM_OPS_BASE_URL is required in prod (config sync/ACK loop)")
		}
		log.Printf("WARN: product-ops-service config sync disabled: PLATFORM_OPS_BASE_URL is empty (env=%s)", appEnv)
		return
	}
	controlplane.RunConfigSyncLoop(controlplane.ConfigSyncLoopOptions{
		BaseURL:       baseURL,
		ServiceName:   serviceName,
		AppEnv:        appEnv,
		ClusterName:   getenvOrDefault("CLUSTER_NAME", appEnv+"-control-a"),
		ConfigRoot:    configRoot,
		ConfigVersion: configVersion,
		ImageVersion:  imageVersion,
		InstanceID:    instanceID,
		HotStore:      hotStore,
	})
}
