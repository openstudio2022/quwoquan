package controlplane

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	rterr "quwoquan_service/runtime/errors"
)

type RateLimitSetter interface {
	SetRate(ratePerSecond int)
	Rate() int
}

type ConfigSyncLoopOptions struct {
	BaseURL       string
	ServiceName   string
	AppEnv        string
	ClusterName   string
	ConfigRoot    string
	ConfigVersion string
	ImageVersion  string
	InstanceID    string
	HotStore      *HotConfigStore
	RateLimiter   RateLimitSetter
}

func RunConfigSyncLoop(opts ConfigSyncLoopOptions) {
	baseURL := strings.TrimSpace(opts.BaseURL)
	if baseURL == "" {
		return
	}

	authorization, err := newConfigSyncServiceAuthorization(opts)
	if err != nil {
		if isProductionConfigSyncEnvironment(opts.AppEnv) {
			panic("controlplane config sync authorization: " + err.Error())
		}
		log.Printf("WARN: controlplane config sync disabled: %v", err)
		return
	}
	client := NewClient(baseURL, &http.Client{Timeout: 4 * time.Second}).
		WithServiceAuthorization(authorization)
	snapshotPath := defaultSnapshotPath(opts.ConfigRoot, opts.ServiceName, opts.InstanceID)

	// 注册运营态错误提示语 override 解析器：闭包持有 HotStore 引用，每次错误出口实时查表，
	// 热配置变更后无需重启即生效；未命中回退 codegen 静态 baseline。
	if opts.HotStore != nil {
		rterr.SetUserMessageResolver(NewErrorMessageResolver(opts.HotStore))
	}

	applyRuntimeSettings := func() {
		if opts.HotStore == nil {
			return
		}
		if opts.RateLimiter != nil {
			opts.RateLimiter.SetRate(opts.HotStore.GetInt("sys.gateway.rate_limit.per_user_rps", opts.RateLimiter.Rate()))
		}
	}

	resolvePollInterval := func() time.Duration {
		seconds := 30
		if opts.HotStore != nil {
			seconds = opts.HotStore.GetInt("sys.config_center.poll_interval_sec", 30)
		}
		if seconds < 5 {
			seconds = 5
		}
		return time.Duration(seconds) * time.Second
	}

	allowDiskFallback := func() bool {
		if isProductionConfigSyncEnvironment(opts.AppEnv) {
			// 生产 ACK 只能证明控制面当前发布包已真实下发；本地磁盘快照
			// 无法证明新 release 生效，故禁止作为 prod 的回退来源。
			return false
		}
		if opts.HotStore == nil {
			return true
		}
		return opts.HotStore.GetBool("sys.config_center.disk_fallback_enabled", true)
	}

	syncOnce := func() {
		scope := ConfigResolutionScope{
			Environment: opts.AppEnv,
			Cluster:     opts.ClusterName,
			Service:     opts.ServiceName,
		}

		ctx, cancel := context.WithTimeout(context.Background(), 4*time.Second)
		defer cancel()

		response, err := client.Resolve(ctx, scope)
		source := "config-center"
		if err != nil {
			if allowDiskFallback() {
				response, err = LoadResolveSnapshot(snapshotPath)
				source = "disk-fallback"
			}
		} else if saveErr := SaveResolveSnapshot(snapshotPath, response); saveErr != nil {
			log.Printf("WARN: controlplane save config snapshot: %v", saveErr)
		}
		if err != nil {
			log.Printf("WARN: controlplane config sync unavailable: %v", err)
			return
		}

		effectiveHash := response.EffectiveHash
		if opts.HotStore != nil {
			effectiveHash = opts.HotStore.Apply(response.Values)
		}
		applyRuntimeSettings()

		report := InstanceConfigReport{
			ID:            opts.InstanceID,
			Environment:   opts.AppEnv,
			Cluster:       opts.ClusterName,
			Service:       opts.ServiceName,
			InstanceID:    opts.InstanceID,
			ConfigVersion: opts.ConfigVersion,
			ImageVersion:  opts.ImageVersion,
			DesiredHash:   response.DesiredHash,
			EffectiveHash: effectiveHash,
			InSync:        response.DesiredHash == effectiveHash,
			Source:        source,
		}
		if report.ID == "" {
			report.ID = opts.ServiceName
		}
		if reportErr := client.ReportInstance(context.Background(), report); reportErr != nil {
			log.Printf("WARN: controlplane config report failed: %v", reportErr)
		}
	}

	syncOnce()
	for {
		timer := time.NewTimer(resolvePollInterval())
		<-timer.C
		timer.Stop()
		syncOnce()
	}
}

func newConfigSyncServiceAuthorization(
	opts ConfigSyncLoopOptions,
) (rtauth.ServiceAuthorizationProvider, error) {
	serviceName := strings.TrimSpace(opts.ServiceName)
	environment := strings.TrimSpace(opts.AppEnv)
	if serviceName == "" || environment == "" {
		return nil, fmt.Errorf("config sync service and environment are required")
	}
	config, err := rtauth.LoadAccessTokenConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		return nil, fmt.Errorf("load config sync service credentials: %w", err)
	}
	return rtauth.NewHS256ServiceAuthorizationProvider(
		config,
		serviceName+"@"+environment,
		[]string{"ops.platform.config.read", "ops.platform.config.ack"},
	)
}

func isProductionConfigSyncEnvironment(appEnv string) bool {
	return strings.EqualFold(strings.TrimSpace(appEnv), "prod")
}

func defaultSnapshotPath(configRoot, serviceName, instanceID string) string {
	if strings.TrimSpace(configRoot) != "" {
		return filepath.Join(configRoot, "runtime-cache", serviceName, instanceID+".json")
	}
	return filepath.Join(defaultOutputRoot(), "env", "repo", "local", "control-plane", "process", serviceName, instanceID+".json")
}

func defaultOutputRoot() string {
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
