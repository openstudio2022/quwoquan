package servicekit

import (
	"context"
	"fmt"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	"quwoquan_service/runtime/controlplane"
	rthealth "quwoquan_service/runtime/health"
)

// configSyncStaleThreshold 是实例侧判定配置同步失联的阈值：同步周期默认
// 30s，连续约 10 个周期无成功同步即视为 stale。
const configSyncStaleThreshold = 5 * time.Minute

var (
	configSyncAttempts = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Namespace: "qwq_config_sync",
			Name:      "attempts_total",
			Help:      "Config sync attempts by service and result (in_sync, out_of_sync, sync_error, report_error).",
		},
		[]string{"service", "result"},
	)
	configSyncInSync = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Namespace: "qwq_config_sync",
			Name:      "in_sync",
			Help:      "Whether the newest sync attempt converged on the desired config (1) or not (0).",
		},
		[]string{"service"},
	)
	configSyncLastSuccess = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Namespace: "qwq_config_sync",
			Name:      "last_success_timestamp_seconds",
			Help:      "Unix timestamp of the newest successful config resolve for this instance.",
		},
		[]string{"service"},
	)
)

// ConfigSyncOptions 控制 RegisterConfigSync 的可选行为。
type ConfigSyncOptions struct {
	// ClusterName 覆盖控制面 cluster 身份；空值取 DefaultClusterName(appEnv)。
	ClusterName string
	// HotStore 覆盖热配置存储；nil 时新建。
	HotStore *controlplane.HotConfigStore
}

// RegisterConfigSync 把持续配置同步/ACK 循环注册为模块标配 worker，并挂接
// 同步指标与 config_sync 健康检查。PLATFORM_OPS_BASE_URL 缺失时：prod 环境
// fail-closed，其余环境跳过注册（本地开发允许无控制面）。
func RegisterConfigSync(
	workers *WorkerRegistry,
	health *rthealth.Checker,
	identity Identity,
	options ConfigSyncOptions,
) (*controlplane.HotConfigStore, error) {
	if workers == nil {
		return nil, fmt.Errorf("%s config sync worker registry is required", identity.ServiceName)
	}
	baseURL := strings.TrimSpace(os.Getenv("PLATFORM_OPS_BASE_URL"))
	if baseURL == "" {
		baseURL = strings.TrimSpace(os.Getenv("VITE_PLATFORM_OPS_BASE_URL"))
	}
	if baseURL == "" {
		if strings.EqualFold(strings.TrimSpace(identity.AppEnv), "prod") {
			return nil, fmt.Errorf(
				"%s PLATFORM_OPS_BASE_URL is required in prod (config sync/ACK loop)",
				identity.ServiceName,
			)
		}
		return nil, nil
	}

	clusterName := resolveConfigSyncClusterName(options.ClusterName, identity.AppEnv)
	hotStore := options.HotStore
	if hotStore == nil {
		hotStore = controlplane.NewHotConfigStore()
	}

	monitor := newConfigSyncMonitor(identity.ServiceName, time.Now)
	if health != nil {
		health.Register("config_sync", func(context.Context) error {
			return monitor.HealthCheck()
		})
	}

	syncOptions := controlplane.ConfigSyncLoopOptions{
		BaseURL:               baseURL,
		ServiceName:           identity.ServiceName,
		AppEnv:                identity.AppEnv,
		ClusterName:           clusterName,
		ConfigRoot:            identity.ConfigRoot,
		ConfigVersion:         identity.ConfigVersion,
		ImageVersion:          identity.ImageVersion,
		ReleaseManifestDigest: strings.TrimSpace(os.Getenv("RELEASE_MANIFEST_DIGEST")),
		InstanceID:            identity.InstanceID,
		HotStore:              hotStore,
		OnSyncResult:          monitor.Observe,
	}
	workers.Add(func(ctx context.Context) {
		controlplane.RunConfigSyncLoopContext(ctx, syncOptions)
	})
	return hotStore, nil
}

// configSyncMonitor 跟踪同步结论，驱动指标与健康检查。启动后尚未产生任何
// 结论时保持健康，避免异步首轮同步阻塞就绪。
type configSyncMonitor struct {
	serviceName string
	now         func() time.Time

	mu            sync.Mutex
	firstObserved time.Time
	lastResult    controlplane.ConfigSyncResult
	lastSuccess   time.Time
}

func newConfigSyncMonitor(serviceName string, now func() time.Time) *configSyncMonitor {
	return &configSyncMonitor{serviceName: serviceName, now: now}
}

func (monitor *configSyncMonitor) Observe(result controlplane.ConfigSyncResult) {
	monitor.mu.Lock()
	defer monitor.mu.Unlock()
	if monitor.firstObserved.IsZero() {
		monitor.firstObserved = monitor.now()
	}
	monitor.lastResult = result

	if result.SyncErr != nil {
		configSyncAttempts.WithLabelValues(monitor.serviceName, "sync_error").Inc()
		configSyncInSync.WithLabelValues(monitor.serviceName).Set(0)
		return
	}
	switch {
	case result.ReportErr != nil:
		configSyncAttempts.WithLabelValues(monitor.serviceName, "report_error").Inc()
	case result.InSync:
		configSyncAttempts.WithLabelValues(monitor.serviceName, "in_sync").Inc()
	default:
		configSyncAttempts.WithLabelValues(monitor.serviceName, "out_of_sync").Inc()
	}

	monitor.lastSuccess = monitor.now()
	configSyncLastSuccess.WithLabelValues(monitor.serviceName).Set(float64(monitor.lastSuccess.Unix()))
	if result.InSync {
		configSyncInSync.WithLabelValues(monitor.serviceName).Set(1)
	} else {
		configSyncInSync.WithLabelValues(monitor.serviceName).Set(0)
	}
}

// HealthCheck 只在同步持续失联超过阈值时报错：距最近一次成功 resolve（从未
// 成功时距首次观察）超过 configSyncStaleThreshold。单次瞬时失败不打爆健康。
func (monitor *configSyncMonitor) HealthCheck() error {
	monitor.mu.Lock()
	defer monitor.mu.Unlock()
	if monitor.firstObserved.IsZero() {
		return nil
	}
	reference := monitor.lastSuccess
	if reference.IsZero() {
		reference = monitor.firstObserved
	}
	if monitor.now().Sub(reference) <= configSyncStaleThreshold {
		return nil
	}
	if monitor.lastResult.SyncErr != nil {
		return fmt.Errorf(
			"%s config sync stale beyond %s: %v",
			monitor.serviceName, configSyncStaleThreshold, monitor.lastResult.SyncErr,
		)
	}
	return fmt.Errorf(
		"%s config sync stale beyond %s",
		monitor.serviceName, configSyncStaleThreshold,
	)
}
