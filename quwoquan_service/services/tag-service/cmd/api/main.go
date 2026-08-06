package main

import (
	"context"
	"fmt"
	"log"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	"gopkg.in/yaml.v3"

	rtmongo "quwoquan_service/internal/platform/mongodb"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	configrelease "quwoquan_service/runtime/configrelease"
	"quwoquan_service/runtime/controlplane"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	signalstream "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/adapters/inbound/stream"
	indexpersistence "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/infrastructure/persistence"
	feedbackhttp "quwoquan_service/services/tag-service/internal/tag/tag_feedback_fact/adapters/inbound/http"
	"quwoquan_service/services/tag-service/internal/tag/tag_feedback_fact/application/tagfeedback"
	"quwoquan_service/services/tag-service/internal/tag/tag_feedback_fact/infrastructure/tagfeedbackstore"
	nodehttp "quwoquan_service/services/tag-service/internal/tag/tag_node_view/adapters/inbound/http"
	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/application"
	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/infrastructure/persistence"
	releasehttp "quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/adapters/inbound/http"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/application/taxonomyrelease"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/infrastructure/taxonomyreleasestore"
)

type config struct {
	Config struct {
		Version string `yaml:"version"`
	} `yaml:"config"`

	Service struct {
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`

	UserAccountSecurityAuthority struct {
		BaseURL   string `yaml:"base_url"`
		TimeoutMs int    `yaml:"timeout_ms"`
	} `yaml:"user_account_security_authority"`

	Mongo struct {
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongo"`

	Redis struct {
		General redisSceneCfg `yaml:"general"`
	} `yaml:"redis"`
}

func main() {
	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		log.Fatalf("tag-service runtime identity invalid: %v", err)
	}

	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		log.Fatalf("tag-service config load failed: %v", err)
	}
	applyEnvOverrides(&cfg)
	if err := validateRuntimeConfigurationIdentity(cfg, configVersion); err != nil {
		log.Fatalf("tag-service config identity failed: %v", err)
	}
	controlplane.StartReleaseConfigAttestation(
		serviceName, appEnv, configRoot, configVersion, imageVersion,
	)

	configProvider := runtimeconfig.EnvRuntimeConfigProvider{}
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(configProvider)
	if err != nil {
		log.Fatalf("tag-service access token config invalid: %v", err)
	}
	accountSecurityAuthorityCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		serviceName,
		[]string{"user.account.security.read"},
	)
	if err != nil {
		log.Fatalf(
			"tag-service account security authority credential init failed: %v",
			err,
		)
	}
	accountSecurityAuthorityTimeout := time.Duration(
		cfg.UserAccountSecurityAuthority.TimeoutMs,
	) * time.Millisecond
	accountSecurityAuthority, err := rtauth.NewHTTPAccountSecurityAuthority(
		rtauth.HTTPAccountSecurityAuthorityConfig{
			BaseURL: cfg.UserAccountSecurityAuthority.BaseURL,
			HTTPClient: &http.Client{
				Timeout: accountSecurityAuthorityTimeout,
			},
			Credentials: accountSecurityAuthorityCredentials,
			Timeout:     accountSecurityAuthorityTimeout,
		},
	)
	if err != nil {
		log.Fatalf("tag-service account security authority config invalid: %v", err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		log.Fatalf("tag-service access token verifier invalid: %v", err)
	}
	deviceTicketConfig, err := rtauth.LoadDeviceTicketConfig(configProvider)
	if err != nil {
		log.Fatalf("tag-service device ticket config invalid: %v", err)
	}
	deviceTicketVerifier, err := rtauth.NewHS256Verifier(deviceTicketConfig)
	if err != nil {
		log.Fatalf("tag-service device ticket verifier invalid: %v", err)
	}

	addr := getenvOrDefault("TAG_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18092"
	}

	ctx := context.Background()

	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "tag-service", SamplingRatio: 0.1})
	defer otelShutdown()

	mongoURI := getenvOrDefault("TAG_MONGO_URI", cfg.Mongo.URI)
	if mongoURI == "" {
		mongoURI = "mongodb://localhost:27017"
	}
	mongoDBName := getenvOrDefault("TAG_MONGO_DATABASE", cfg.Mongo.Database)
	if mongoDBName == "" {
		mongoDBName = "quwoquan_tag"
	}

	mongoClient := rtmongo.MustConnect(ctx, rtmongo.ConnectConfig{URI: mongoURI}, "tag-service")
	defer mongoClient.Disconnect(ctx)

	db := mongoClient.Database(mongoDBName)
	tagNodeStore := persistence.NewMongoTagNodeStore(db.Collection("tag_nodes"))
	objectTagStore := indexpersistence.NewMongoObjectTagIndexStore(db.Collection("object_tag_index"))
	if err := tagNodeStore.EnsureIndexes(ctx); err != nil {
		log.Fatalf("tag-service ensure tag_nodes indexes: %v", err)
	}
	if err := objectTagStore.EnsureIndexes(ctx); err != nil {
		log.Fatalf("tag-service ensure object_tag_index indexes: %v", err)
	}

	releaseStore := taxonomyreleasestore.NewStore(db)
	if err := releaseStore.EnsureIndexes(ctx); err != nil {
		log.Fatalf("tag-service ensure tag_taxonomy_releases indexes: %v", err)
	}
	tagService := application.NewTagService(tagNodeStore, objectTagStore, releaseStore)
	releaseFacade, err := taxonomyrelease.NewFacade(releaseStore, tagNodeStore)
	if err != nil {
		log.Fatalf("tag-service taxonomy release facade init failed: %v", err)
	}
	feedbackSink := tagfeedbackstore.NewSink(db)
	if err := feedbackSink.EnsureIndexes(ctx); err != nil {
		log.Fatalf("tag-service ensure tag_feedback_fact indexes: %v", err)
	}
	feedbackFacade, err := tagfeedback.NewFacade(feedbackSink, tagService)
	if err != nil {
		log.Fatalf("tag-service tag feedback facade init failed: %v", err)
	}

	redisRouter, redisSceneModes := buildTagRedisRouter(cfg)
	defer redisRouter.Close()
	messageTransport, err := requireTagAPIMessageTransport(
		ctx,
		appEnv,
		redisRouter,
		redisSceneModes,
	)
	if err != nil {
		log.Fatalf("tag-service message transport init failed: %v", err)
	}
	profileTagConsumer, err := signalstream.NewUserProfileTagConsumer(
		messageTransport,
		objectTagStore,
		serviceName,
		slog.Default(),
	)
	if err != nil {
		log.Fatalf("tag-service user profile tag consumer init failed: %v", err)
	}
	go profileTagConsumer.Run(ctx)
	feedbackEventPublisher, err := tagfeedbackstore.NewStreamEventPublisher(
		messageTransport,
	)
	if err != nil {
		log.Fatalf("tag-service feedback event publisher init failed: %v", err)
	}
	feedbackEventRelay, err := tagfeedbackstore.NewEventRelay(
		feedbackSink,
		feedbackEventPublisher,
		slog.Default(),
	)
	if err != nil {
		log.Fatalf("tag-service feedback event relay init failed: %v", err)
	}
	go feedbackEventRelay.Run(ctx)

	routesMux := http.NewServeMux()
	nodehttp.NewTagHandler(tagService).Register(routesMux)
	releasehttp.NewTaxonomyReleaseHandler(releaseFacade).Register(routesMux)
	feedbackhttp.NewTagFeedbackHandler(feedbackFacade).Register(routesMux)
	generatedOperationGuard := rtauth.RequireGeneratedOperationAuthorization(
		operationsecurity.ForDomain("tag"),
	)(routesMux)

	healthChecker := rthealth.NewChecker()
	healthChecker.Register("account-security-authority", func(hctx context.Context) error {
		return accountSecurityAuthority.CheckAccountSecurityAuthority(hctx)
	})
	healthChecker.Register("mongodb", func(hctx context.Context) error {
		return mongoClient.Ping(hctx, nil)
	})
	healthChecker.Register("taxonomy-projection", func(hctx context.Context) error {
		release, found, err := releaseStore.FindActive(hctx)
		if err != nil {
			return err
		}
		if !found {
			return fmt.Errorf("active taxonomy release is missing")
		}
		return tagNodeStore.ValidateReleaseProjection(
			hctx,
			release.ReleaseID,
			release.NodeCount,
		)
	})
	healthChecker.Register("redis", redisRouter.PingAll)
	healthChecker.Register("profile-tag-consumer", func(context.Context) error {
		return profileTagConsumer.Healthy(15 * time.Second)
	})
	healthChecker.Register("feedback-event-relay", func(hctx context.Context) error {
		return feedbackEventRelay.Healthy(hctx, 15*time.Second)
	})

	outerMux := http.NewServeMux()
	outerMux.HandleFunc("/healthz", healthChecker.Handler())
	outerMux.Handle("/metrics", rtmetrics.Handler())
	outerMux.Handle("/", generatedOperationGuard)

	instanceID, _ := os.Hostname()
	// 服务日志上云：stdout/stderr 镜像推送到 Product Ops 内部 runtime log
	// ingest（机器凭据）；未配置时仅 stdout，推送失败静默降级。
	runtimeLogExporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		log.Fatalf("tag-service runtime log exporter init failed: %v", err)
	}
	defer runtimeLogExporter.Close()
	standardLogWriter := robs.NewRuntimeLogExportWriter(os.Stdout, 512, runtimeLogExporter.Export)
	errorLogWriter := robs.NewRuntimeLogExportWriter(os.Stderr, 512, runtimeLogExporter.Export)
	defer standardLogWriter.Close()
	defer errorLogWriter.Close()
	ioLogger := robs.NewIOAccessLogger(standardLogWriter)
	processLogger, err := robs.NewProcessTraceLogger(standardLogWriter, errorLogWriter, "info", nil)
	if err != nil {
		log.Fatalf("tag-service process logger init failed: %v", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(standardLogWriter, errorLogWriter, nil)
	if err != nil {
		log.Fatalf("tag-service exception logger init failed: %v", err)
	}
	observed := rthttp.NewHTTPServerMiddleware(outerMux, rthttp.HTTPServerMiddlewareConfig{
		Service:           "tag-service",
		ServiceName:       "tag-service",
		ServiceInstanceID: instanceID,
	}, ioLogger, processLogger, exceptionLogger)
	corsHandler := rthttp.WithCORS(observed, rthttp.CORSOptionsFromEnv())

	timeouts := rtauth.ContractHTTPServerTimeouts(
		operationsecurity.ForDomain("tag"),
	)
	server := &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:      accessVerifier,
			DeviceTicketVerifier:     deviceTicketVerifier,
			AccountSecurityAuthority: accountSecurityAuthority,
		})(corsHandler),
		ReadHeaderTimeout: timeouts.ReadHeader,
		WriteTimeout:      timeouts.Write,
		IdleTimeout:       timeouts.Idle,
	}
	log.Printf("tag-service listening on %s (env=%s)", addr, appEnv)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("tag-service: %v", err)
	}
}

func resolveRuntimeIdentity() (serviceName, appEnv, configRoot, configVersion, imageVersion string, err error) {
	serviceName = getenvOrDefault("SERVICE_NAME", "tag-service")
	appEnv = getenvOrDefault("APP_ENV", "alpha")
	configRoot = os.Getenv("CONFIG_ROOT")
	configVersion = os.Getenv("CONFIG_VERSION")
	imageVersion = os.Getenv("IMAGE_VERSION")

	if !isValidAppEnv(appEnv) {
		return "", "", "", "", "", fmt.Errorf("APP_ENV must be one of alpha|beta|gamma|prod, got %q", appEnv)
	}
	if requiresConfigVersion(appEnv) && strings.TrimSpace(configVersion) == "" {
		return "", "", "", "", "", fmt.Errorf("CONFIG_VERSION is required when APP_ENV=%s", appEnv)
	}
	return serviceName, appEnv, configRoot, configVersion, imageVersion, nil
}

func isValidAppEnv(env string) bool {
	switch env {
	case "alpha", "beta", "gamma", "prod":
		return true
	default:
		return false
	}
}

func requiresConfigVersion(env string) bool {
	switch env {
	case "gamma", "prod":
		return true
	default:
		return false
	}
}

func getenvOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion string) (config, error) {
	cfg := config{}
	path, err := configrelease.File(configRoot, serviceName, appEnv)
	if err != nil {
		return config{}, err
	}
	if err := mergeConfigFile(&cfg, path); err != nil {
		return config{}, fmt.Errorf("read generated runtime config: %w", err)
	}
	return cfg, nil
}

func mergeConfigFile(cfg *config, path string) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	if err := yaml.Unmarshal(raw, cfg); err != nil {
		return fmt.Errorf("parse %s: %w", path, err)
	}
	return nil
}

func applyEnvOverrides(cfg *config) {
	if v := os.Getenv("TAG_MONGO_URI"); v != "" {
		cfg.Mongo.URI = v
	}
	if v := os.Getenv("TAG_MONGO_DATABASE"); v != "" {
		cfg.Mongo.Database = v
	}
	applyTagRedisEnvOverrides(&cfg.Redis.General)
}

func validateRuntimeConfigurationIdentity(cfg config, configVersion string) error {
	if strings.TrimSpace(configVersion) != "" && strings.TrimSpace(cfg.Config.Version) != "" && cfg.Config.Version != configVersion {
		return fmt.Errorf("CONFIG_VERSION mismatch: env=%s file=%s", configVersion, cfg.Config.Version)
	}
	return nil
}
