package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

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
		return
	}

	clusterName := getenvOrDefault("CLUSTER_NAME", defaultClusterName(appEnv))
	client := controlplane.NewClient(baseURL, &http.Client{Timeout: 4 * time.Second})
	snapshotPath := resolveSnapshotPath(configRoot, serviceName, instanceID)

	syncOnce := func() {
		scope := controlplane.ConfigResolutionScope{
			Environment: appEnv,
			Cluster:     clusterName,
			Service:     serviceName,
		}

		ctx, cancel := context.WithTimeout(context.Background(), 4*time.Second)
		defer cancel()

		response, err := client.Resolve(ctx, scope)
		source := "config-center"
		if err != nil {
			response, err = controlplane.LoadResolveSnapshot(snapshotPath)
			source = "disk-fallback"
		} else if saveErr := controlplane.SaveResolveSnapshot(snapshotPath, response); saveErr != nil {
			log.Printf("WARN: product-ops-service save config snapshot: %v", saveErr)
		}
		if err != nil {
			log.Printf("WARN: product-ops-service config sync unavailable: %v", err)
			return
		}

		effectiveHash := hotStore.Apply(response.Values)

		report := controlplane.InstanceConfigReport{
			ID:            instanceID,
			Environment:   appEnv,
			Cluster:       clusterName,
			Service:       serviceName,
			InstanceID:    instanceID,
			ConfigVersion: configVersion,
			ImageVersion:  imageVersion,
			DesiredHash:   response.DesiredHash,
			EffectiveHash: effectiveHash,
			InSync:        response.DesiredHash == effectiveHash,
			Source:        source,
		}
		if reportErr := client.ReportInstance(context.Background(), report); reportErr != nil {
			log.Printf("WARN: product-ops-service config report failed: %v", reportErr)
		}
	}

	syncOnce()
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()
	for range ticker.C {
		syncOnce()
	}
}

func resolveSnapshotPath(configRoot, serviceName, instanceID string) string {
	if strings.TrimSpace(configRoot) != "" {
		return filepath.Join(configRoot, "runtime-cache", serviceName, instanceID+".json")
	}
	return filepath.Join("state", "runtime-cache", serviceName, instanceID+".json")
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
