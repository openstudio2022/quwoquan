package servicekit

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"quwoquan_service/runtime/controlplane"
	rthealth "quwoquan_service/runtime/health"
)

func clearConfigSyncEnvironment(t *testing.T) {
	t.Helper()
	t.Setenv("PLATFORM_OPS_BASE_URL", "")
	t.Setenv("VITE_PLATFORM_OPS_BASE_URL", "")
	t.Setenv("RELEASE_MANIFEST_DIGEST", "")
}

func TestRegisterConfigSyncFailsClosedInProdWithoutControlPlane(t *testing.T) {
	clearConfigSyncEnvironment(t)
	workers := &WorkerRegistry{}
	identity := Identity{ServiceName: "circle-service", AppEnv: "prod"}
	_, err := RegisterConfigSync(workers, rthealth.NewChecker(), identity, ConfigSyncOptions{})
	if err == nil || !strings.Contains(err.Error(), "PLATFORM_OPS_BASE_URL") {
		t.Fatalf("expected prod fail-closed, got %v", err)
	}
}

func TestRegisterConfigSyncSkipsWhenControlPlaneAbsentOutsideProd(t *testing.T) {
	clearConfigSyncEnvironment(t)
	workers := &WorkerRegistry{}
	identity := Identity{ServiceName: "circle-service", AppEnv: "alpha"}
	hotStore, err := RegisterConfigSync(workers, rthealth.NewChecker(), identity, ConfigSyncOptions{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if hotStore != nil {
		t.Fatal("expected no hot store without a control plane")
	}
	if len(workers.starts) != 0 {
		t.Fatal("expected no sync worker without a control plane")
	}
}

func TestRegisterConfigSyncRegistersWorkerAndHealthCheck(t *testing.T) {
	clearConfigSyncEnvironment(t)
	t.Setenv("PLATFORM_OPS_BASE_URL", "http://platform-ops.internal:18090")
	workers := &WorkerRegistry{}
	health := rthealth.NewChecker()
	identity := Identity{
		ServiceName:   "circle-service",
		AppEnv:        "alpha",
		InstanceID:    "pod-1",
		ImageVersion:  "sha256:abc",
		ConfigVersion: "sha256:cfg",
	}
	hotStore, err := RegisterConfigSync(workers, health, identity, ConfigSyncOptions{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if hotStore == nil {
		t.Fatal("expected a hot config store")
	}
	if len(workers.starts) != 1 {
		t.Fatalf("expected exactly one sync worker, got %d", len(workers.starts))
	}
	result := health.Check(context.Background())
	if result.Status != "ok" {
		t.Fatalf("config_sync health must stay ok before the first attempt: %+v", result)
	}
}

// TestResolveConfigSyncClusterNamePrefersInjection 锁定 cluster 身份来源优先级：
// 服务显式声明 > 部署面注入的 CLUSTER_NAME > 按环境派生的默认值。prod rollout
// 按 prod-<instance>-control-<replica> 逐副本注入 CLUSTER_NAME，若被派生默认值
// 覆盖，全体副本会在实例报告里自称同一个 cluster。
func TestResolveConfigSyncClusterNamePrefersInjection(t *testing.T) {
	t.Setenv("CLUSTER_NAME", "")
	if name := resolveConfigSyncClusterName("", "prod"); name != "prod-control-a" {
		t.Fatalf("absent injection must fall back to the derived default, got %s", name)
	}

	t.Setenv("CLUSTER_NAME", "prod-b-control-2")
	if name := resolveConfigSyncClusterName("", "prod"); name != "prod-b-control-2" {
		t.Fatalf("deployment injection must win over the derived default, got %s", name)
	}
	if name := resolveConfigSyncClusterName("declared-control-a", "prod"); name != "declared-control-a" {
		t.Fatalf("explicit declaration must win over injection, got %s", name)
	}

	t.Setenv("CLUSTER_NAME", "   ")
	if name := resolveConfigSyncClusterName("", "gamma"); name != "gamma-control-a" {
		t.Fatalf("blank injection must not become the cluster identity, got %q", name)
	}
}

func TestConfigSyncMonitorHealthTransitions(t *testing.T) {
	current := time.Unix(1_700_000_000, 0)
	monitor := newConfigSyncMonitor("circle-service", func() time.Time { return current })

	if err := monitor.HealthCheck(); err != nil {
		t.Fatalf("monitor must be healthy before any observation: %v", err)
	}

	monitor.Observe(controlplane.ConfigSyncResult{SyncErr: errors.New("resolve unavailable")})
	if err := monitor.HealthCheck(); err != nil {
		t.Fatalf("one transient failure must not trip health: %v", err)
	}

	current = current.Add(configSyncStaleThreshold + time.Minute)
	err := monitor.HealthCheck()
	if err == nil || !strings.Contains(err.Error(), "stale") {
		t.Fatalf("expected stale failure after threshold without success, got %v", err)
	}

	monitor.Observe(controlplane.ConfigSyncResult{InSync: true, Source: "config-center"})
	if err := monitor.HealthCheck(); err != nil {
		t.Fatalf("successful sync must restore health: %v", err)
	}

	current = current.Add(configSyncStaleThreshold + time.Minute)
	if err := monitor.HealthCheck(); err == nil {
		t.Fatal("expected stale failure when success stops arriving")
	}

	monitor.Observe(controlplane.ConfigSyncResult{InSync: false, Source: "config-center"})
	if err := monitor.HealthCheck(); err != nil {
		t.Fatalf("out-of-sync resolve still proves liveness: %v", err)
	}
}
