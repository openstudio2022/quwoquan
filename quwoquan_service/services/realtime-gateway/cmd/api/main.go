// realtime-gateway：统一实时通信网关（runtime_session）。
// 职责最小化：ticket 鉴权、WS/LongPoll 连接管理（lease+fencing+presence）、
// 按可信身份订阅 Redis realtime scene 并透传事件。不承载任何业务聚合。
package main

import (
	"context"
	"fmt"
	"log"
	"log/slog"
	"net"
	"net/http"
	"os"
	"strings"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	platformredis "quwoquan_service/internal/platform/redis"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	rtredis "quwoquan_service/runtime/redis"
	httpadapter "quwoquan_service/services/realtime-gateway/internal/adapters/http"
	wsadapter "quwoquan_service/services/realtime-gateway/internal/adapters/ws"
	"quwoquan_service/services/realtime-gateway/internal/application"
	"quwoquan_service/services/realtime-gateway/internal/infrastructure/redisstore"
)

func main() {
	if err := run(); err != nil {
		log.Fatalf("realtime-gateway: %v", err)
	}
}

func run() error {
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		return fmt.Errorf("access token config invalid: %w", err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		return fmt.Errorf("access token verifier invalid: %w", err)
	}
	deviceTicketConfig, err := rtauth.LoadDeviceTicketConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		return fmt.Errorf("device ticket config invalid: %w", err)
	}
	deviceVerifier, err := rtauth.NewHS256Verifier(deviceTicketConfig)
	if err != nil {
		return fmt.Errorf("device ticket verifier invalid: %w", err)
	}

	ctx, cancelRuntime := context.WithCancel(context.Background())
	defer cancelRuntime()
	otelShutdown := rtotel.MustInit(rtotel.Config{
		ServiceName:   "realtime-gateway",
		SamplingRatio: 0.1,
	})
	defer otelShutdown()

	redisRouter, err := buildRedisRouter()
	if err != nil {
		return err
	}
	defer redisRouter.Close()
	realtimeClient := redisRouter.Scene("realtime")
	if err := realtimeClient.Ping(ctx); err != nil {
		if failFastEnvironment() {
			return fmt.Errorf("realtime redis unavailable: %w", err)
		}
		log.Printf("WARN: realtime-gateway redis ping: %v", err)
	}

	logger := slog.Default()
	nodeID := getenvOrDefault("SERVICE_INSTANCE_ID", hostname())

	ticketStore := redisstore.NewTicketStore(realtimeClient)
	leaseStore := redisstore.NewLeaseStore(realtimeClient)
	presenceStore := redisstore.NewPresenceStore(realtimeClient)
	eventSource := redisstore.NewEventSource(realtimeClient)

	tickets, err := application.NewTicketService(ticketStore)
	if err != nil {
		return err
	}
	hub, err := application.NewHub(leaseStore, presenceStore, eventSource, nodeID, logger)
	if err != nil {
		return err
	}
	handler, err := httpadapter.NewHandler(
		tickets,
		eventSource,
		presenceStore,
		presenceStore,
		httpadapter.DefaultTransportConfig(),
		nodeID,
		logger,
	)
	if err != nil {
		return err
	}
	upgradeHandler, err := wsadapter.NewHandler(tickets, hub, logger)
	if err != nil {
		return err
	}

	guarded := http.NewServeMux()
	handler.Routes(guarded)

	rootMux := http.NewServeMux()
	rootMux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
	rootMux.Handle("/metrics", rtmetrics.Handler())
	// WS 升级不经 operation guard：鉴权由一次性 ticket 承载（浏览器 WS
	// 握手无法携带 Bearer header），契约见 connection/service.yaml。
	rootMux.HandleFunc("GET /realtime/ws", upgradeHandler.HandleUpgrade)
	rootMux.Handle(
		"/",
		rtauth.RequireGeneratedOperationAuthorization(
			operationsecurity.ForDomain("realtime"),
		)(guarded),
	)

	// 服务日志上云：stdout/stderr 镜像推送到 Product Ops 内部 runtime log
	// ingest（机器凭据）；未配置时仅 stdout，推送失败静默降级。
	runtimeLogExporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		log.Fatalf("realtime-gateway runtime log exporter init failed: %v", err)
	}
	defer runtimeLogExporter.Close()
	standardLogWriter := robs.NewRuntimeLogExportWriter(os.Stdout, 512, runtimeLogExporter.Export)
	errorLogWriter := robs.NewRuntimeLogExportWriter(os.Stderr, 512, runtimeLogExporter.Export)
	defer standardLogWriter.Close()
	defer errorLogWriter.Close()
	ioLogger := robs.NewIOAccessLogger(standardLogWriter)
	kvFilter := robs.NewKVMetadataFilter(nil)
	processLogger, err := robs.NewProcessTraceLogger(
		standardLogWriter,
		errorLogWriter,
		robs.TraceLogLevelInfo,
		kvFilter,
	)
	if err != nil {
		return fmt.Errorf("process logger init failed: %w", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(standardLogWriter, errorLogWriter, kvFilter)
	if err != nil {
		return fmt.Errorf("exception logger init failed: %w", err)
	}
	withObservability := rthttp.NewHTTPServerMiddleware(
		rootMux,
		rthttp.HTTPServerMiddlewareConfig{
			Service:           "realtime-gateway",
			Origin:            "cloud",
			Direction:         "inbound",
			SourceID:          "realtime-gateway.http",
			Src:               "gateway",
			ServiceName:       "realtime-gateway",
			ServiceInstanceID: nodeID,
		},
		ioLogger,
		processLogger,
		exceptionLogger,
	)

	addr := getenvOrDefault("REALTIME_GATEWAY_ADDR", ":18090")
	server := &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:  accessVerifier,
			DeviceTicketVerifier: deviceVerifier,
		})(withObservability),
		BaseContext:       func(_ net.Listener) context.Context { return ctx },
		ReadHeaderTimeout: 5 * time.Second,
		// WS/LongPoll 是长连接工作负载，不设整体 WriteTimeout。
		IdleTimeout: 120 * time.Second,
	}
	log.Printf("realtime-gateway listening on %s", server.Addr)
	return rthttp.ListenAndServeGraceful(server, 15*time.Second)
}

func buildRedisRouter() (*rtredis.Router, error) {
	sceneConfig := rtredis.SceneConfig{
		Mode:     getenvOrDefault("REALTIME_REDIS_MODE", "memory"),
		Addr:     strings.TrimSpace(os.Getenv("REALTIME_REDIS_ADDR")),
		Password: os.Getenv("REALTIME_REDIS_PASSWORD"),
	}
	if addrs := strings.TrimSpace(os.Getenv("REALTIME_REDIS_ADDRS")); addrs != "" {
		sceneConfig.Addrs = strings.Split(addrs, ",")
	}
	if failFastEnvironment() && sceneConfig.Mode == "memory" {
		return nil, fmt.Errorf(
			"REALTIME_REDIS_MODE=memory is forbidden in %s",
			getenvOrDefault("APP_ENV", ""),
		)
	}
	return platformredis.NewRouter(rtredis.RouterConfig{
		Scenes:       map[string]rtredis.SceneConfig{"realtime": sceneConfig},
		DefaultScene: "realtime",
	})
}

func failFastEnvironment() bool {
	switch strings.TrimSpace(os.Getenv("APP_ENV")) {
	case "beta", "gamma", "prod":
		return true
	default:
		return false
	}
}

func getenvOrDefault(key string, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

func hostname() string {
	name, err := os.Hostname()
	if err != nil || strings.TrimSpace(name) == "" {
		return "realtime-gateway-local"
	}
	return name
}
