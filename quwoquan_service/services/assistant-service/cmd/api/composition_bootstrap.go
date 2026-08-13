package bootstrap

import (
	"context"
	"crypto/sha256"
	"fmt"
	"log"
	"os"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/controlplane"
	rthealth "quwoquan_service/runtime/health"
	runtimemessaging "quwoquan_service/runtime/messaging"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	rtredis "quwoquan_service/runtime/redis"
)

type assistantAPIRuntime struct {
	appEnv                   string
	configDigest             string
	config                   config
	addr                     string
	instanceID               string
	accessTokenConfig        rtauth.TokenConfig
	accessVerifier           *rtauth.Verifier
	accountSecurityAuthority *rtauth.HTTPAccountSecurityAuthority
	runtimeLogExporter       *robs.HTTPRuntimeLogExporter
	standardLogWriter        *robs.RuntimeLogExportWriter
	errorLogWriter           *robs.RuntimeLogExportWriter
	ioLogger                 *robs.IOAccessLogger
	processLogger            *robs.ProcessTraceLogger
	exceptionLogger          *robs.ExceptionLogger
}

func bootstrapAssistantAPIRuntime() (*assistantAPIRuntime, error) {
	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		return nil, fmt.Errorf("runtime identity invalid: %w", err)
	}
	runtimeConfigProvider := runtimeconfig.EnvRuntimeConfigProvider{}
	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		return nil, fmt.Errorf("config load failed: %w", err)
	}
	if err := applyEnvOverrides(&cfg); err != nil {
		return nil, fmt.Errorf("environment override invalid: %w", err)
	}
	if err := validateRuntimeConfigurationIdentity(cfg, configVersion); err != nil {
		return nil, fmt.Errorf("config identity failed: %w", err)
	}
	if err := validateRuntimeDependenciesConfig(cfg); err != nil {
		return nil, err
	}
	controlplane.StartReleaseConfigAttestation(
		serviceName, appEnv, configRoot, configVersion, imageVersion,
	)
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(runtimeConfigProvider)
	if err != nil {
		return nil, fmt.Errorf("access token config invalid: %w", err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		return nil, fmt.Errorf("access token verifier invalid: %w", err)
	}
	accountSecurityAuthority, err := buildAccountSecurityAuthority(
		cfg,
		accessTokenConfig,
	)
	if err != nil {
		return nil, err
	}
	addr := getenvOrDefault("ASSISTANT_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18087"
	}
	instanceID := assistantModuleEnvironmentValue("SERVICE_INSTANCE_ID", hostname())

	runtimeLogExporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		return nil, fmt.Errorf("runtime log exporter init failed: %w", err)
	}
	standardLogWriter := robs.NewRuntimeLogExportWriter(
		os.Stdout,
		512,
		runtimeLogExporter.Export,
	)
	errorLogWriter := robs.NewRuntimeLogExportWriter(
		os.Stderr,
		512,
		runtimeLogExporter.Export,
	)
	ioLogger := robs.NewIOAccessLogger(standardLogWriter)
	processLogger, err := robs.NewProcessTraceLogger(
		standardLogWriter,
		errorLogWriter,
		robs.TraceLogLevelInfo,
		nil,
	)
	if err != nil {
		closeRuntimeLogPipeline(runtimeLogExporter, standardLogWriter, errorLogWriter)
		return nil, fmt.Errorf("process logger init failed: %w", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(
		standardLogWriter,
		errorLogWriter,
		nil,
	)
	if err != nil {
		closeRuntimeLogPipeline(runtimeLogExporter, standardLogWriter, errorLogWriter)
		return nil, fmt.Errorf("exception logger init failed: %w", err)
	}
	return &assistantAPIRuntime{
		appEnv:                   appEnv,
		configDigest:             fmt.Sprintf("%x", sha256.Sum256([]byte(fmt.Sprintf("%#v:%s", cfg, configVersion)))),
		config:                   cfg,
		addr:                     addr,
		instanceID:               instanceID,
		accessTokenConfig:        accessTokenConfig,
		accessVerifier:           accessVerifier,
		accountSecurityAuthority: accountSecurityAuthority,
		runtimeLogExporter:       runtimeLogExporter,
		standardLogWriter:        standardLogWriter,
		errorLogWriter:           errorLogWriter,
		ioLogger:                 ioLogger,
		processLogger:            processLogger,
		exceptionLogger:          exceptionLogger,
	}, nil
}

func (runtime *assistantAPIRuntime) Close() {
	if runtime == nil {
		return
	}
	closeRuntimeLogPipeline(
		runtime.runtimeLogExporter,
		runtime.standardLogWriter,
		runtime.errorLogWriter,
	)
}

func closeRuntimeLogPipeline(
	exporter *robs.HTTPRuntimeLogExporter,
	standardWriter *robs.RuntimeLogExportWriter,
	errorWriter *robs.RuntimeLogExportWriter,
) {
	if errorWriter != nil {
		errorWriter.Close()
	}
	if standardWriter != nil {
		standardWriter.Close()
	}
	if exporter != nil {
		exporter.Close()
	}
}

type assistantInfrastructure struct {
	router           *rtredis.Router
	messageTransport *runtimemessaging.RedisMessageTransport
	healthChecker    *rthealth.Checker
	dependencies     *persistentDependencies
	otelShutdown     func()
}

func bootstrapAssistantInfrastructure(
	runtime *assistantAPIRuntime,
) (*assistantInfrastructure, error) {
	ctx := context.Background()
	router, err := buildRedisRouter(runtime.config)
	if err != nil {
		return nil, err
	}
	redisProbeCtx, redisProbeCancel := context.WithTimeout(ctx, dependencyProbeTimeout)
	if err := router.PingAll(redisProbeCtx); err != nil {
		redisProbeCancel()
		closeRedisRouter(router)
		return nil, dependencyError("redis", "connectivity", err)
	}
	redisProbeCancel()
	messageTransport, err := requireAssistantAPIMessageTransport(
		ctx,
		runtime.appEnv,
		router,
		map[string]string{"general": runtime.config.Redis.General.Mode},
	)
	if err != nil {
		closeRedisRouter(router)
		return nil, dependencyError("runtime.message.transport", "preflight", err)
	}
	otelShutdown := rtotel.MustInit(rtotel.Config{
		ServiceName:   "assistant-service",
		SamplingRatio: 0.1,
	})
	healthChecker := rthealth.NewChecker()
	registerAccountSecurityAuthorityHealth(
		healthChecker,
		runtime.accountSecurityAuthority,
		router,
	)

	deps, err := openPersistentDependencies(ctx, runtime.config)
	if err != nil {
		otelShutdown()
		closeRedisRouter(router)
		return nil, err
	}
	healthChecker.Register("mongodb", func(ctx context.Context) error {
		return deps.mongoClient.Ping(ctx, nil)
	})
	healthChecker.Register("postgres", func(ctx context.Context) error {
		return deps.postgresPool.Ping(ctx)
	})
	log.Printf("assistant-service events storage=mongodb db=%s", runtime.config.MongoDB.Database)
	log.Printf("assistant-service learning projection storage=mongodb db=%s", runtime.config.MongoDB.Database)
	log.Printf("assistant-service skill subscription storage=mongodb db=%s", runtime.config.MongoDB.Database)
	log.Printf("assistant-service consent storage=postgres")
	log.Printf("assistant-service Skill setting/placement storage=postgres")
	return &assistantInfrastructure{
		router:           router,
		messageTransport: messageTransport,
		healthChecker:    healthChecker,
		dependencies:     deps,
		otelShutdown:     otelShutdown,
	}, nil
}

func (infrastructure *assistantInfrastructure) Close() {
	if infrastructure == nil {
		return
	}
	if infrastructure.dependencies != nil {
		closeCtx, cancel := context.WithTimeout(
			context.Background(),
			dependencyProbeTimeout,
		)
		if err := infrastructure.dependencies.Close(closeCtx); err != nil {
			log.Printf("WARN: assistant-service persistent dependency close: %v", err)
		}
		cancel()
	}
	if infrastructure.otelShutdown != nil {
		infrastructure.otelShutdown()
	}
	closeRedisRouter(infrastructure.router)
}

func closeRedisRouter(router *rtredis.Router) {
	if router == nil {
		return
	}
	if err := router.Close(); err != nil {
		log.Printf("WARN: assistant-service redis close: %v", err)
	}
}
