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
		// beta/gamma/prod 的配置热更与 drift 检测依赖该地址；生产缺失必须
		// fail-fast，禁止静默跳过后伪装"配置中心可用"。
		if strings.EqualFold(strings.TrimSpace(appEnv), "prod") {
			log.Fatal("product-ops-service PLATFORM_OPS_BASE_URL is required in prod (config sync/ACK loop)")
		}
		log.Printf("WARN: product-ops-service config sync disabled: PLATFORM_OPS_BASE_URL is empty (env=%s)", appEnv)
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
	return filepath.Join(resolveLocalOutputRoot(), "env", "repo", "local", "control-plane", "process", serviceName, instanceID+".json")
}

func resolveLocalOutputRoot() string {
	if outputRoot := strings.TrimSpace(os.Getenv("QWQ_OUTPUT_ROOT")); outputRoot != "" {
		return outputRoot
	}
	if cwd, err := os.Getwd(); err == nil {
		for dir := cwd; ; dir = filepath.Dir(dir) {
			if directoryExists(filepath.Join(dir, "quwoquan_service")) &&
				directoryExists(filepath.Join(dir, "quwoquan_ops")) {
				return filepath.Join(dir, ".qwq_output")
			}
			parent := filepath.Dir(dir)
			if parent == dir {
				break
			}
		}
	}
	return filepath.Join(os.TempDir(), "quwoquan", ".qwq_output")
}

func directoryExists(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.IsDir()
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
