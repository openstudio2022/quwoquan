package main

import (
	"context"
	"log"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	rtmongo "quwoquan_service/runtime/mongodb"

	rtgov "quwoquan_service/runtime/governance"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	httpadapter "quwoquan_service/services/assistant-service/internal/adapters/http"
	"quwoquan_service/services/assistant-service/internal/application"
	"quwoquan_service/services/assistant-service/internal/infrastructure/chatclient"
	"quwoquan_service/services/assistant-service/internal/infrastructure/messaging"
	"quwoquan_service/services/assistant-service/internal/infrastructure/persistence"
	"quwoquan_service/services/assistant-service/internal/infrastructure/projection"
	"quwoquan_service/services/assistant-service/internal/infrastructure/userprofile"
)

func main() {
	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		log.Fatalf("assistant-service runtime identity invalid: %v", err)
	}
	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		log.Fatalf("assistant-service config load failed: %v", err)
	}
	applyEnvOverrides(&cfg)
	if err := validateRuntimeCompatibility(cfg, configVersion, imageVersion); err != nil {
		log.Fatalf("assistant-service config compatibility failed: %v", err)
	}
	addr := getenvOrDefault("ASSISTANT_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18087"
	}
	instanceID := getenvOrDefault("SERVICE_INSTANCE_ID", hostname())
	ioLogger := robs.NewIOAccessLogger(os.Stdout)
	processLogger, err := robs.NewProcessTraceLogger(os.Stdout, os.Stderr, robs.TraceLogLevelInfo, nil)
	if err != nil {
		log.Fatalf("assistant-service process logger init failed: %v", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(os.Stdout, os.Stderr, nil)
	if err != nil {
		log.Fatalf("assistant-service exception logger init failed: %v", err)
	}
	router := buildRedisRouter(cfg)
	defer router.Close()
	if err := router.PingAll(context.Background()); err != nil {
		log.Printf("WARN: assistant-service redis PingAll: %v", err)
	}
	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "assistant-service", SamplingRatio: 0.1})
	defer otelShutdown()

	healthChecker := rthealth.NewChecker()
	healthChecker.Register("redis", func(ctx context.Context) error {
		return router.PingAll(ctx)
	})

	ctx := context.Background()

	var eventStore application.EventStore
	var profileStore application.LearningProfileStore
	var subscriptionStore application.SkillSubscriptionStore
	var appMessageStore application.AppMessageStore
	if strings.TrimSpace(cfg.MongoDB.URI) != "" {
		mongoClient := rtmongo.MustConnect(ctx, rtmongo.ConnectConfig{URI: cfg.MongoDB.URI}, "assistant-service")
		defer func() {
			shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			_ = mongoClient.Disconnect(shutdownCtx)
		}()
		dbName := cfg.MongoDB.Database
		if strings.TrimSpace(dbName) == "" {
			dbName = "quwoquan_assistant"
		}
		db := mongoClient.Database(dbName)
		mongoStore := persistence.NewMongoEventStore(db)
		if err := mongoStore.EnsureIndexes(ctx); err != nil {
			log.Printf("WARN: assistant-service ensure mongo indexes: %v", err)
		}
		eventStore = mongoStore
		mongoProfiles := projection.NewLearningProfileStore(db)
		if err := mongoProfiles.EnsureIndexes(ctx); err != nil {
			log.Printf("WARN: assistant-service ensure learning profile indexes: %v", err)
		}
		profileStore = mongoProfiles
		mongoSubscriptions := persistence.NewMongoSkillSubscriptionStore(db)
		if err := mongoSubscriptions.EnsureIndexes(ctx); err != nil {
			log.Printf("WARN: assistant-service ensure skill subscription indexes: %v", err)
		}
		subscriptionStore = mongoSubscriptions
		mongoAppMessages := persistence.NewMongoAppMessageStore(db)
		if err := mongoAppMessages.EnsureIndexes(ctx); err != nil {
			log.Printf("WARN: assistant-service ensure app message indexes: %v", err)
		}
		appMessageStore = mongoAppMessages
		healthChecker.Register("mongodb", func(ctx context.Context) error {
			return mongoClient.Ping(ctx, nil)
		})
		log.Printf("assistant-service events storage=mongodb db=%s", dbName)
		log.Printf("assistant-service learning profile storage=mongodb db=%s", dbName)
		log.Printf("assistant-service skill subscription storage=mongodb db=%s", dbName)
		log.Printf("assistant-service app message storage=mongodb db=%s", dbName)
	} else {
		eventStore = persistence.NewMemoryEventStore()
		profileStore = projection.NewMemoryLearningProfileStore()
		subscriptionStore = persistence.NewMemorySkillSubscriptionStore()
		appMessageStore = persistence.NewMemoryAppMessageStore()
		log.Printf("assistant-service events storage=inmemory (no mongodb.uri configured)")
		log.Printf("assistant-service learning profile storage=inmemory (no mongodb.uri configured)")
		log.Printf("assistant-service skill subscription storage=inmemory (no mongodb.uri configured)")
		log.Printf("assistant-service app message storage=inmemory (no mongodb.uri configured)")
	}

	var consentStore application.ConsentStore
	if strings.TrimSpace(cfg.Postgres.DSN) != "" {
		poolCfg, err := pgxpool.ParseConfig(cfg.Postgres.DSN)
		if err != nil {
			log.Fatalf("assistant-service postgres parse failed: %v", err)
		}
		if cfg.Postgres.MaxOpenConns > 0 {
			poolCfg.MaxConns = int32(cfg.Postgres.MaxOpenConns)
		}
		if cfg.Postgres.MaxIdleConns > 0 {
			poolCfg.MinConns = int32(cfg.Postgres.MaxIdleConns)
		}
		if cfg.Postgres.ConnMaxLifetimeMinutes > 0 {
			poolCfg.MaxConnLifetime = time.Duration(cfg.Postgres.ConnMaxLifetimeMinutes) * time.Minute
		}
		pgPool, err := pgxpool.NewWithConfig(ctx, poolCfg)
		if err != nil {
			log.Fatalf("assistant-service postgres connect failed: %v", err)
		}
		defer pgPool.Close()
		if err := pgPool.Ping(ctx); err != nil {
			log.Printf("WARN: assistant-service postgres ping: %v", err)
		}
		healthChecker.Register("postgres", func(ctx context.Context) error {
			return pgPool.Ping(ctx)
		})
		pgStore := persistence.NewPgConsentStore(pgPool)
		if err := pgStore.EnsureSchema(ctx); err != nil {
			log.Printf("WARN: assistant-service ensure pg schema: %v", err)
		}
		consentStore = pgStore
		log.Printf("assistant-service consent storage=postgres")
	} else {
		consentStore = persistence.NewMemoryConsentStore()
		log.Printf("assistant-service consent storage=inmemory (no postgres.dsn configured)")
	}

	publisher := messaging.NewRedisEventPublisher(router.Scene("general"), serviceName, nil)
	assistantOpts := []application.AssistantServiceOption{
		application.WithLearningProfileStore(profileStore),
		application.WithEventPublisher(publisher),
		application.WithAppMessageStore(appMessageStore),
		application.WithSkillSubscriptionStore(subscriptionStore),
		application.WithAgentLoop(buildAgentLoop(cfg, appEnv)),
	}
	chatGroundingEnabled := false
	if userProfileBase := strings.TrimSpace(cfg.UserProfile.BaseURL); userProfileBase != "" {
		interestReader := userprofile.NewClient(searchHTTPClient(cfg.UserProfile.TimeoutMs), userProfileBase)
		assistantOpts = append(assistantOpts, application.WithProactiveInterestReader(interestReader))
		log.Printf("assistant-service proactive interest profile reader enabled base=%s", userProfileBase)
	} else {
		log.Printf("assistant-service proactive interest profile reader disabled (no user_profile.base_url)")
	}
	if chatBase := strings.TrimSpace(cfg.ChatService.BaseURL); chatBase != "" {
		assistantOpts = append(assistantOpts, application.WithChatGroundingClient(chatclient.NewClient(searchHTTPClient(cfg.ChatService.TimeoutMs), chatBase)))
		chatGroundingEnabled = true
		log.Printf("assistant-service chat grounding client enabled base=%s", chatBase)
	} else {
		log.Printf("assistant-service chat grounding client disabled (no chat_service.base_url)")
	}
	service := application.NewAssistantService(
		eventStore,
		consentStore,
		router.Scene("general"),
		assistantOpts...,
	)
	if seedRefs := scenarioSeedRefsFromEnv(); len(seedRefs) > 0 {
		pack, err := application.LoadAssistantScenarioPack()
		if err != nil {
			log.Fatalf("assistant-service scenario seed load failed: %v", err)
		}
		if err := application.SeedAssistantServiceFromScenarioPack(ctx, service, "user_m11_scenario", pack, seedRefs); err != nil {
			log.Fatalf("assistant-service scenario seed failed: %v", err)
		}
		log.Printf("assistant-service scenario seed loaded refs=%s", strings.Join(seedRefs, ","))
	}
	if chatGroundingEnabled {
		consumer := messaging.NewAssistantMentionedConsumer(
			router.Scene("general"),
			service,
			instanceID,
			slog.Default(),
		)
		go consumer.Run(context.Background(), 500*time.Millisecond)
		log.Printf("assistant-service assistant mentioned consumer enabled stream=%s group=%s", messaging.AssistantMentionedStream, messaging.AssistantMentionedConsumerGroup)
	}
	baseHandler := httpadapter.NewHandler(service).Routes()
	outerMux := http.NewServeMux()
	outerMux.HandleFunc("/healthz", healthChecker.Handler())
	outerMux.Handle("/metrics", rtmetrics.Handler())
	outerMux.Handle("/", baseHandler)
	observedHandler := rthttp.NewHTTPServerMiddleware(outerMux, rthttp.HTTPServerMiddlewareConfig{
		Service:           "assistant-service",
		ServiceName:       "assistant-service",
		ServiceInstanceID: instanceID,
		Origin:            "service.http",
		Direction:         robs.DirectionInbound,
		SourceID:          "assistant-service",
		Src:               "assistant-service",
	}, ioLogger, processLogger, exceptionLogger)
	corsHandler := rthttp.WithCORS(observedHandler, rthttp.CORSOptionsFromEnv())
	rateLimiter := rtgov.NewRateLimiter(1000)
	rateLimited := rtgov.RateLimitMiddleware(rateLimiter)(corsHandler)
	server := &http.Server{Addr: addr, Handler: rateLimited, ReadHeaderTimeout: 5 * time.Second, WriteTimeout: assistantHTTPWriteTimeout(), IdleTimeout: 60 * time.Second}
	log.Printf("assistant-service listening on %s env=%s (rate_limit=1000/s)", addr, appEnv)
	if err := rthttp.ListenAndServeGraceful(server, assistantShutdownTimeout()); err != nil {
		log.Fatalf("assistant-service listen failed: %v", err)
	}
}
