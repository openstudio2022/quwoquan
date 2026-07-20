package main

import (
	"context"
	"fmt"
	"log"
	"log/slog"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"gopkg.in/yaml.v3"

	"quwoquan_service/generated/operationsecurity"
	rtmongo "quwoquan_service/internal/platform/mongodb"
	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/reliabletaskmongo"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	rthealth "quwoquan_service/runtime/health"
	rtotel "quwoquan_service/runtime/otel"

	rterr "quwoquan_service/runtime/errors"
	rtgov "quwoquan_service/runtime/governance"
	rthttp "quwoquan_service/runtime/http"
	runtimemedia "quwoquan_service/runtime/media"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/reliabletask"
	runtimesync "quwoquan_service/runtime/sync"
	httpadapter "quwoquan_service/services/chat-service/internal/adapters/http"
	"quwoquan_service/services/chat-service/internal/adapters/mq"
	"quwoquan_service/services/chat-service/internal/application"
	chatcache "quwoquan_service/services/chat-service/internal/infrastructure/cache"
	messageexternal "quwoquan_service/services/chat-service/internal/infrastructure/chat/message/external"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

type redisSceneCfg struct {
	Mode     string   `yaml:"mode"`
	Addr     string   `yaml:"addr"`
	Addrs    []string `yaml:"addrs"`
	Password string   `yaml:"password"`
	DB       int      `yaml:"db"`
	TLS      bool     `yaml:"tls"`
	Pool     struct {
		Size    int `yaml:"size"`
		MinIdle int `yaml:"min_idle"`
	} `yaml:"pool"`
}

type config struct {
	Config struct {
		Version         string `yaml:"version"`
		MinImageVersion string `yaml:"min_image_version"`
		MaxImageVersion string `yaml:"max_image_version"`
	} `yaml:"config"`

	Service struct {
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`

	MongoDB struct {
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongodb"`

	Redis struct {
		Realtime     redisSceneCfg `yaml:"realtime"`
		General      redisSceneCfg `yaml:"general"`
		ReliableTask redisSceneCfg `yaml:"reliable_task"`
	} `yaml:"redis"`

	Runtime struct {
		Media struct {
			GroupAvatarCDNBaseURL     string `yaml:"group_avatar_cdn_base_url"`
			GroupAvatarLocalMediaRoot string `yaml:"group_avatar_local_media_root"`
		} `yaml:"media"`
		Sync struct {
			PatchTTLHours int `yaml:"patch_ttl_hours"`
		} `yaml:"sync"`
		ReliableTask struct {
			ReadyIndex struct {
				Enabled bool   `yaml:"enabled"`
				Stream  string `yaml:"stream"`
				Group   string `yaml:"group"`
				Queue   string `yaml:"queue"`
			} `yaml:"ready_index"`
		} `yaml:"reliable_task"`
		Observability struct {
			RuntimeMedia struct {
				GroupAvatarRecomputeDurationMsP95 float64 `yaml:"group_avatar_recompute_duration_ms_p95"`
				GroupAvatarFallbackRatio          float64 `yaml:"group_avatar_fallback_ratio"`
				HintToPullDelayMsP95              float64 `yaml:"hint_to_pull_delay_ms_p95"`
				PatchFanoutFailureRatio           float64 `yaml:"patch_fanout_failure_ratio"`
			} `yaml:"runtime_media"`
		} `yaml:"observability"`
	} `yaml:"runtime"`
}

func main() {
	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		log.Fatalf("chat-service runtime identity invalid: %v", err)
	}

	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		log.Fatalf("chat-service config load failed: %v", err)
	}
	applyEnvOverrides(&cfg)
	if err := validateRuntimeCompatibility(cfg, configVersion, imageVersion); err != nil {
		log.Fatalf("chat-service config compatibility failed: %v", err)
	}
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		log.Fatalf("chat-service access token config invalid: %v", err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		log.Fatalf("chat-service access token verifier invalid: %v", err)
	}
	addr := getenvOrDefault("CHAT_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18081"
	}

	logger := slog.Default()
	instanceID := getenvOrDefault("SERVICE_INSTANCE_ID", hostname())
	userServiceBaseURL, err := requireInternalServiceBaseURL(
		"USER_SERVICE_BASE_URL",
		os.Getenv("USER_SERVICE_BASE_URL"),
	)
	if err != nil {
		log.Fatalf("chat-service user dependency invalid: %v", err)
	}
	circleServiceBaseURL := strings.TrimSpace(os.Getenv("CIRCLE_SERVICE_BASE_URL"))
	if circleServiceBaseURL == "" {
		circleServiceBaseURL = strings.TrimSpace(os.Getenv("GATEWAY_BASE_URL"))
	}
	circleServiceBaseURL, err = requireInternalServiceBaseURL(
		"CIRCLE_SERVICE_BASE_URL or GATEWAY_BASE_URL",
		circleServiceBaseURL,
	)
	if err != nil {
		log.Fatalf("chat-service circle dependency invalid: %v", err)
	}
	contentServiceBaseURL, err := requireInternalServiceBaseURL(
		"CONTENT_SERVICE_BASE_URL",
		os.Getenv("CONTENT_SERVICE_BASE_URL"),
	)
	if err != nil {
		log.Fatalf("chat-service content dependency invalid: %v", err)
	}

	// 服务日志上云：stdout/stderr 镜像推送到 Product Ops 内部 runtime log
	// ingest（机器凭据）；未配置时仅 stdout，推送失败静默降级。
	runtimeLogExporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		log.Fatalf("chat-service runtime log exporter init failed: %v", err)
	}
	defer runtimeLogExporter.Close()
	standardLogWriter := robs.NewRuntimeLogExportWriter(os.Stdout, 512, runtimeLogExporter.Export)
	errorLogWriter := robs.NewRuntimeLogExportWriter(os.Stderr, 512, runtimeLogExporter.Export)
	defer standardLogWriter.Close()
	defer errorLogWriter.Close()
	ioLogger := robs.NewIOAccessLogger(standardLogWriter)
	processLogger, err := robs.NewProcessTraceLogger(standardLogWriter, errorLogWriter, "info", nil)
	if err != nil {
		log.Fatalf("chat-service process logger init failed: %v", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(standardLogWriter, errorLogWriter, nil)
	if err != nil {
		log.Fatalf("chat-service exception logger init failed: %v", err)
	}

	router := buildRedisRouter(cfg)
	defer router.Close()

	ctx, cancelRuntime := context.WithCancel(context.Background())

	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "chat-service", SamplingRatio: 0.1})
	defer otelShutdown()

	if err := router.PingAll(ctx); err != nil {
		log.Fatalf("chat-service redis dependency unavailable: %v", err)
	}
	mongoClient := rtmongo.MustConnect(ctx, rtmongo.ConnectConfig{URI: cfg.MongoDB.URI}, "chat-service")
	defer func() {
		cancelRuntime()
		disconnectCtx, cancelDisconnect := context.WithTimeout(
			context.Background(),
			5*time.Second,
		)
		defer cancelDisconnect()
		_ = mongoClient.Disconnect(disconnectCtx)
	}()

	mongoDB := mongoClient.Database(cfg.MongoDB.Database)
	chatStore := persistence.NewMongoChatStore(mongoDB)
	if err := chatStore.EnsureIndexes(ctx); err != nil {
		log.Fatalf("chat-service aggregate indexes unavailable: %v", err)
	}
	conversationCommands := persistence.NewMongoAggregateCommandStore(
		mongoDB, "conversations_command_receipts", "conversations_outbox",
	)
	membershipCommands := persistence.NewMongoAggregateCommandStore(
		mongoDB, "conversation_memberships_command_receipts", "conversation_memberships_outbox",
	)
	userStateCommands := persistence.NewMongoAggregateCommandStore(
		mongoDB, "conversation_user_states_command_receipts", "conversation_user_states_outbox",
	)
	for _, commands := range []*persistence.MongoAggregateCommandStore{
		conversationCommands, membershipCommands, userStateCommands,
	} {
		if err := commands.EnsureIndexes(ctx); err != nil {
			log.Fatalf("chat-service aggregate command indexes unavailable: %v", err)
		}
	}
	userAccountClosedProjection := persistence.NewMongoUserAccountClosedProjection(
		mongoDB,
		router.Scene("general"),
	)
	if err := userAccountClosedProjection.EnsureIndexes(ctx); err != nil {
		log.Fatalf("chat-service UserAccountClosed indexes unavailable: %v", err)
	}
	userAccountClosedConsumer, err := mq.NewUserAccountClosedConsumer(
		router.Scene("general"),
		userAccountClosedProjection,
		userAccountClosedProjection,
		"chat-user-account-closed:"+instanceID,
		logger,
		mq.DefaultUserAccountClosedConsumerConfig(),
	)
	if err != nil {
		log.Fatalf("chat-service UserAccountClosed consumer invalid: %v", err)
	}
	if err := userAccountClosedConsumer.EnsureGroup(ctx); err != nil {
		log.Fatalf("chat-service UserAccountClosed consumer group unavailable: %v", err)
	}
	projectionCheckpoints := persistence.NewMongoProjectionCheckpointStore(mongoDB)
	chatStorage := application.ChatStoragePorts{
		Transactions:         chatStore,
		Conversations:        chatStore,
		Messages:             chatStore,
		MessageProjection:    chatStore,
		Members:              chatStore,
		UserStates:           chatStore,
		Receipts:             chatStore,
		ConversationCommands: conversationCommands,
		MembershipCommands:   membershipCommands,
		UserStateCommands:    userStateCommands,
	}
	convCache := chatcache.NewConversationCache(router.Scene("general"))
	// 实时扇出接收者必须分页拉全量成员：单页上限截断会让大群
	// （maxGroupSize 默认 1000 > 单页 512）静默漏推实时事件。
	recipientResolver := mq.NewMemberRecipientResolver(
		func(ctx context.Context, conversationID string) ([]string, error) {
			const fanoutPageSize = 512
			ids := make([]string, 0, fanoutPageSize)
			cursor := ""
			for {
				members, err := chatStore.ListMembers(
					ctx,
					conversationID,
					application.ListMembersQuery{
						Limit:  fanoutPageSize,
						Cursor: cursor,
						Sort:   application.MemberListSortJoinedAsc,
					},
				)
				if err != nil {
					return nil, err
				}
				for _, member := range members {
					ids = append(ids, member.UserId)
				}
				if len(members) < fanoutPageSize {
					return ids, nil
				}
				last := members[len(members)-1]
				cursor = persistence.EncodeMemberListNextCursorJoined(last.JoinedAt, last.ID)
			}
		},
	)
	eventPublisher := mq.NewEventPublisher(router.Scene("realtime"), recipientResolver)
	messageOutboxRelay := application.NewMessageOutboxRelay(
		chatStore,
		chatStore,
		chatStore,
		eventPublisher,
		"chat-runtime-fanout",
	)
	go func() {
		if err := messageOutboxRelay.Run(ctx, 100*time.Millisecond); err != nil {
			logger.Error("chat message outbox relay stopped", "err", err)
		}
	}()
	// 三个非 Message 聚合共享 relay 骨架，各自 outbox 独立 checkpoint；
	// 保留 relay 引用供 /healthz 与 Prometheus 检测停滞，而不是只在 goroutine
	// 退出时留一条不可告警的日志。
	aggregateOutboxRelays := map[string]*application.AggregateOutboxRelay{}
	for _, spec := range []struct {
		healthName string
		consumer   string
		source     *persistence.MongoAggregateCommandStore
	}{
		{
			healthName: "conversation_outbox_relay",
			consumer:   "chat-conversation-outbox-fanout",
			source:     conversationCommands,
		},
		{
			healthName: "membership_outbox_relay",
			consumer:   "chat-membership-outbox-fanout",
			source:     membershipCommands,
		},
		{
			healthName: "user_state_outbox_relay",
			consumer:   "chat-user-state-outbox-fanout",
			source:     userStateCommands,
		},
	} {
		relay := application.NewAggregateOutboxRelay(
			spec.source, projectionCheckpoints, eventPublisher, spec.consumer,
		)
		aggregateOutboxRelays[spec.healthName] = relay
		go func(name string, relay *application.AggregateOutboxRelay) {
			if err := relay.Run(ctx, 100*time.Millisecond); err != nil {
				logger.Error("chat aggregate outbox relay stopped", "consumer", name, "err", err)
			}
		}(spec.consumer, relay)
	}
	// ChatInbox 未读/排序投影：独立 checkpoint 消费 Message outbox。
	inboxProjector := application.NewInboxProjector(
		chatStore, projectionCheckpoints, chatStore, chatStore,
	)
	go func() {
		if err := inboxProjector.Run(ctx, 200*time.Millisecond); err != nil {
			logger.Error("chat inbox projector stopped", "err", err)
		}
	}()
	localMediaRoot := strings.TrimSpace(cfg.Runtime.Media.GroupAvatarLocalMediaRoot)
	if localMediaRoot == "" {
		localMediaRoot = "./var/chat-media"
	}
	application.ConfigureGroupAvatarCDNBase(cfg.Runtime.Media.GroupAvatarCDNBaseURL)
	if err := runtimemedia.EnsureDefaultGroupAvatarFile(localMediaRoot); err != nil {
		log.Fatalf("chat-service default group avatar init failed: %v", err)
	}
	groupAvatarMedia := runtimemedia.NewGroupAvatarService(
		router.Scene("general"),
		cfg.Runtime.Media.GroupAvatarCDNBaseURL,
		localMediaRoot,
	)
	syncOptions := []runtimesync.Option{}
	if cfg.Runtime.Sync.PatchTTLHours > 0 {
		syncOptions = append(
			syncOptions,
			runtimesync.WithPatchTTL(time.Duration(cfg.Runtime.Sync.PatchTTLHours)*time.Hour),
		)
	}
	userSyncService := runtimesync.NewService(
		router.Scene("general"),
		router.Scene("realtime"),
		syncOptions...,
	)
	reliableTaskCatalog, err := loadReliableTaskCatalog(configRoot)
	if err != nil {
		log.Fatalf("chat-service reliable task catalog load failed: %v", err)
	}
	reliableTaskStore := reliabletaskmongo.New(mongoDB)
	if err := reliableTaskStore.EnsureIndexes(ctx); err != nil {
		log.Fatalf("chat-service reliable task index init failed: %v", err)
	}
	var reliableTaskReadyIndex reliabletask.ReadyIndex
	if cfg.Runtime.ReliableTask.ReadyIndex.Enabled {
		index, err := reliabletask.NewRedisReadyIndex(reliabletask.RedisReadyIndexConfig{
			Client: router.Scene("reliabletask"),
			Stream: cfg.Runtime.ReliableTask.ReadyIndex.Stream,
			Group:  cfg.Runtime.ReliableTask.ReadyIndex.Group,
			Queue:  cfg.Runtime.ReliableTask.ReadyIndex.Queue,
		})
		if err != nil {
			log.Fatalf("chat-service reliable task redis ready index init failed: %v", err)
		}
		if err := index.Ensure(ctx); err != nil {
			log.Fatalf("chat-service reliable task redis ready index ensure failed: %v", err)
		}
		reliableTaskReadyIndex = index
	}
	groupAvatarScheduler := application.NewReliableGroupAvatarTaskScheduler(
		reliableTaskStore,
		reliableTaskCatalog,
		chatStorage,
		eventPublisher,
		groupAvatarMedia,
		userSyncService,
		logger,
		application.WithReliableGroupAvatarRuntimeIdentity(appEnv, instanceID),
		application.WithReliableGroupAvatarEnabledModules(resolveReliableTaskModules()),
		application.WithReliableGroupAvatarReadyIndex(reliableTaskReadyIndex),
	)
	if err := groupAvatarScheduler.Start(ctx); err != nil {
		log.Fatalf("chat-service reliable group avatar scheduler start failed: %v", err)
	}
	go func() {
		if err := application.BackfillMissingGroupAvatars(
			context.Background(),
			chatStorage,
			eventPublisher,
			groupAvatarMedia,
			userSyncService,
			groupAvatarScheduler,
			200,
		); err != nil {
			logger.Error("chat-service group avatar backfill failed", "err", err)
		}
	}()
	profileCB := rtgov.NewCircuitBreaker(5, 15*time.Second, slog.Default())
	profileClient := rtgov.WrapClientWithCB(&http.Client{Timeout: 2 * time.Second}, profileCB)
	profileResolver := httpadapter.NewUserProfileResolver(userServiceBaseURL, profileClient)
	relationshipGate := httpadapter.NewUserRelationshipGate(userServiceBaseURL, profileClient)
	socialContactResolver := httpadapter.NewUserSocialContactResolver(userServiceBaseURL, profileClient)
	circleListResolver := httpadapter.NewCircleListResolverClient(circleServiceBaseURL, profileClient)
	contentCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"chat-service",
		[]string{"content.media.delivery.read"},
	)
	if err != nil {
		log.Fatalf("content-service delivery credential init failed: %v", err)
	}
	mediaAssetReader, err := messageexternal.NewMediaAssetDeliveryReader(
		contentServiceBaseURL,
		contentCredentials,
		nil,
	)
	if err != nil {
		log.Fatalf("content-service MediaAsset delivery reader invalid: %v", err)
	}

	conversationSvc := application.NewConversationService(
		chatStorage,
		convCache,
		eventPublisher,
		profileResolver,
		relationshipGate,
		groupAvatarMedia,
		userSyncService,
		groupAvatarScheduler,
	)
	messageSvc := application.NewMessageService(
		chatStorage,
		convCache,
		eventPublisher,
		relationshipGate,
		mediaAssetReader,
	)
	// 公告即触达：公告命令发布成功后经消息主线写 system_announcement 消息。
	conversationSvc.SetAnnouncementMessageSender(messageSvc)
	rtcCallLogConsumer := mq.NewRtcCallEndedConsumer(
		router.Scene("realtime"),
		messageSvc,
		instanceID,
	)
	go func() {
		for {
			if err := rtcCallLogConsumer.Run(ctx); err != nil {
				if ctx.Err() != nil {
					return
				}
				logger.Error("chat rtc CallEnded consumer stopped", "error", err)
				time.Sleep(time.Second)
				continue
			}
			return
		}
	}()
	memberSvc := application.NewMemberService(
		chatStorage,
		convCache,
		eventPublisher,
		profileResolver,
		groupAvatarMedia,
		userSyncService,
		groupAvatarScheduler,
		application.WithRelationshipGate(relationshipGate),
		application.WithSocialContactResolver(socialContactResolver),
		application.WithCircleListResolver(circleListResolver),
	)
	inboxSvc := application.NewInboxService(chatStorage)
	userAvatarConsumer := mq.NewUserAvatarUpdateConsumer(
		router.Scene("general"),
		chatStorage,
		eventPublisher,
		groupAvatarMedia,
		userSyncService,
		groupAvatarScheduler,
		logger,
	)
	if err := userAvatarConsumer.Start(ctx); err != nil {
		log.Fatalf("chat-service user avatar consumer start failed: %v", err)
	}
	userAccountClosedStopped := make(chan struct{})
	go func() {
		defer close(userAccountClosedStopped)
		userAccountClosedConsumer.Run(ctx)
	}()
	defer func() {
		cancelRuntime()
		select {
		case <-userAccountClosedStopped:
		case <-time.After(5 * time.Second):
			logger.Error("chat UserAccountClosed consumer shutdown timed out")
		}
	}()
	healthChecker := rthealth.NewChecker()
	healthChecker.Register("redis", func(hctx context.Context) error {
		return router.PingAll(hctx)
	})
	healthChecker.Register("mongodb", func(hctx context.Context) error {
		return mongoClient.Ping(hctx, nil)
	})
	healthChecker.Register("message_outbox_relay", func(context.Context) error {
		return messageOutboxRelay.Healthy(5 * time.Second)
	})
	for name, aggregateRelay := range aggregateOutboxRelays {
		relay := aggregateRelay
		healthChecker.Register(name, func(context.Context) error {
			return relay.Healthy(5 * time.Second)
		})
	}
	healthChecker.Register("inbox_projection", func(context.Context) error {
		return inboxProjector.Healthy(5 * time.Second)
	})
	healthChecker.Register("user_account_closed_consumer", func(context.Context) error {
		return userAccountClosedConsumer.Healthy(15 * time.Second)
	})

	chatRoutes := httpadapter.NewChatHandler(
		conversationSvc,
		messageSvc,
		memberSvc,
		inboxSvc,
		userSyncService,
	).Routes()
	baseHandler := rtauth.RequireGeneratedOperationAuthorization(
		operationsecurity.ForDomain("chat"),
	)(chatRoutes)
	rootMux := http.NewServeMux()
	rootMux.HandleFunc("/healthz", healthChecker.Handler())
	rootMux.Handle("/metrics", rtmetrics.Handler())
	rootMux.Handle("/media/", newDerivedMediaFileServer(localMediaRoot))
	rootMux.Handle("/metrics/runtime-media", application.NewRuntimeMediaMetricsHandler(
		groupAvatarScheduler,
		userSyncService,
		application.RuntimeMediaAlertThresholds{
			GroupAvatarRecomputeDurationMsP95: cfg.Runtime.Observability.RuntimeMedia.GroupAvatarRecomputeDurationMsP95,
			GroupAvatarFallbackRatio:          cfg.Runtime.Observability.RuntimeMedia.GroupAvatarFallbackRatio,
			HintToPullDelayMsP95:              cfg.Runtime.Observability.RuntimeMedia.HintToPullDelayMsP95,
			PatchFanoutFailureRatio:           cfg.Runtime.Observability.RuntimeMedia.PatchFanoutFailureRatio,
		},
	))
	rootMux.Handle("/", baseHandler)
	observedHandler := rthttp.NewHTTPServerMiddleware(rootMux, rthttp.HTTPServerMiddlewareConfig{
		Service:           "chat-service",
		ServiceName:       "chat-service",
		ServiceInstanceID: instanceID,
		Origin:            "service.http",
		Direction:         robs.DirectionInbound,
		SourceID:          "chat-service",
		Src:               "chat-service",
	}, ioLogger, processLogger, exceptionLogger)
	corsHandler := rthttp.WithCORS(observedHandler, rthttp.CORSOptionsFromEnv())

	rateLimiter := rtgov.NewRateLimiter(1000)
	rateLimited := rtgov.RateLimitMiddleware(rateLimiter)(corsHandler)

	server := &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier: accessVerifier,
		})(rateLimited),
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	logger.Info("chat-service starting", "addr", addr, "env", appEnv)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("chat-service: %v", err)
	}
}

func resolveRuntimeIdentity() (serviceName, appEnv, configRoot, configVersion, imageVersion string, err error) {
	serviceName = getenvOrDefault("SERVICE_NAME", "chat-service")
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

func requireInternalServiceBaseURL(name, raw string) (string, error) {
	value := strings.TrimRight(strings.TrimSpace(raw), "/")
	if value == "" {
		return "", fmt.Errorf("%s is required", name)
	}
	parsed, err := url.Parse(value)
	if err != nil ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") ||
		parsed.Host == "" || parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" {
		return "", fmt.Errorf("%s must be an absolute http(s) origin without credentials, query, or fragment", name)
	}
	if parsed.Path != "" {
		return "", fmt.Errorf("%s must not contain a path", name)
	}
	return value, nil
}

func hostname() string {
	h, err := os.Hostname()
	if err != nil {
		return "unknown"
	}
	return h
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

func loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion string) (config, error) {
	cfg := config{}

	if strings.TrimSpace(configRoot) != "" {
		defaultFile := filepath.Join(configRoot, "configs", serviceName, "default", "config.yaml")
		envFile := filepath.Join(configRoot, "configs", serviceName, appEnv, "config.yaml")

		if err := mergeConfigFile(&cfg, defaultFile); err != nil {
			return config{}, fmt.Errorf("read default config: %w", err)
		}
		if err := mergeConfigFile(&cfg, envFile); err != nil {
			return config{}, fmt.Errorf("read env config: %w", err)
		}
		if strings.TrimSpace(configVersion) != "" {
			versionFile := filepath.Join(configRoot, "quwoquan_service", "services", serviceName, "configs", "releases", configVersion+".yaml")
			if err := mergeConfigFile(&cfg, versionFile); err != nil {
				return config{}, fmt.Errorf("read version config: %w", err)
			}
		}
		return cfg, nil
	}

	localDefault := filepath.Join("configs", "default", "config.yaml")
	localEnv := filepath.Join("configs", appEnv, "config.yaml")
	if err := mergeConfigFile(&cfg, localDefault); err != nil {
		return config{}, fmt.Errorf("read local default config: %w", err)
	}
	if err := mergeConfigFile(&cfg, localEnv); err != nil {
		return config{}, fmt.Errorf("read local env config: %w", err)
	}
	if strings.TrimSpace(configVersion) != "" {
		versionFile := filepath.Join("configs", "releases", configVersion+".yaml")
		if err := mergeConfigFile(&cfg, versionFile); err != nil {
			return config{}, fmt.Errorf("read local version config: %w", err)
		}
	}
	return cfg, nil
}

func loadReliableTaskCatalog(configRoot string) (reliabletask.Catalog, error) {
	type pair struct {
		catalog string
		policy  string
	}
	pairs := []pair{}
	if path := strings.TrimSpace(os.Getenv("RELIABLE_TASK_CATALOG_PATH")); path != "" {
		policyPath := strings.TrimSpace(os.Getenv("RELIABLE_TASK_RETENTION_POLICY_PATH"))
		pairs = append(pairs, pair{catalog: path, policy: policyPath})
	}
	if strings.TrimSpace(configRoot) != "" {
		pairs = append(pairs, pair{
			catalog: filepath.Join(configRoot, "quwoquan_ops", "environments", "reliable_task_module_catalog.yaml"),
			policy:  filepath.Join(configRoot, "quwoquan_ops", "environments", "reliable_task_retention_policy.yaml"),
		})
	}
	pairs = append(pairs,
		pair{catalog: "quwoquan_ops/environments/reliable_task_module_catalog.yaml", policy: "quwoquan_ops/environments/reliable_task_retention_policy.yaml"},
		pair{catalog: "../quwoquan_ops/environments/reliable_task_module_catalog.yaml", policy: "../quwoquan_ops/environments/reliable_task_retention_policy.yaml"},
	)
	var lastErr error
	for _, candidate := range pairs {
		var catalog reliabletask.Catalog
		var err error
		if candidate.policy != "" {
			catalog, err = reliabletask.LoadCatalogWithPolicies(candidate.catalog, candidate.policy)
		} else {
			catalog, err = reliabletask.LoadCatalog(candidate.catalog)
		}
		if err == nil {
			return catalog, nil
		}
		lastErr = err
	}
	return reliabletask.Catalog{}, lastErr
}

func resolveReliableTaskModules() []string {
	if raw := strings.TrimSpace(os.Getenv("RELIABLE_TASK_MODULES")); raw != "" {
		return splitCSV(raw)
	}
	switch strings.TrimSpace(os.Getenv("MODULE_PACKAGE")) {
	case "chat-avatar-worker-package":
		return []string{"chat.group_avatar_worker"}
	case "chat-background-package":
		return []string{"chat.task_outbox_dispatcher", "chat.notification_outbox_dispatcher", "notification.fanout_worker"}
	case "seed-box", "chat-service", "quwoquan_service", "":
		return []string{
			"chat.task_outbox_dispatcher",
			"chat.group_avatar_worker",
			"chat.notification_outbox_dispatcher",
			"notification.fanout_worker",
		}
	default:
		return []string{
			"chat.task_outbox_dispatcher",
			"chat.group_avatar_worker",
			"chat.notification_outbox_dispatcher",
			"notification.fanout_worker",
		}
	}
}

func splitCSV(raw string) []string {
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		trimmed := strings.TrimSpace(part)
		if trimmed != "" {
			out = append(out, trimmed)
		}
	}
	return out
}

func validateRuntimeCompatibility(cfg config, configVersion, imageVersion string) error {
	if strings.TrimSpace(configVersion) != "" && strings.TrimSpace(cfg.Config.Version) != "" && cfg.Config.Version != configVersion {
		return fmt.Errorf("CONFIG_VERSION mismatch: env=%s file=%s", configVersion, cfg.Config.Version)
	}
	if strings.TrimSpace(imageVersion) == "" {
		return nil
	}
	if cfg.Config.MinImageVersion != "" && compareSemver(imageVersion, cfg.Config.MinImageVersion) < 0 {
		return fmt.Errorf("IMAGE_VERSION=%s below min_image_version=%s", imageVersion, cfg.Config.MinImageVersion)
	}
	if cfg.Config.MaxImageVersion != "" && compareSemver(imageVersion, cfg.Config.MaxImageVersion) > 0 {
		return fmt.Errorf("IMAGE_VERSION=%s above max_image_version=%s", imageVersion, cfg.Config.MaxImageVersion)
	}
	return nil
}

func compareSemver(a, b string) int {
	parse := func(v string) [3]int {
		var out [3]int
		parts := strings.Split(strings.TrimPrefix(strings.TrimSpace(v), "v"), ".")
		for i := 0; i < len(parts) && i < 3; i++ {
			n, _ := strconv.Atoi(parts[i])
			out[i] = n
		}
		return out
	}
	av := parse(a)
	bv := parse(b)
	for i := 0; i < 3; i++ {
		if av[i] > bv[i] {
			return 1
		}
		if av[i] < bv[i] {
			return -1
		}
	}
	return 0
}

func newDerivedMediaFileServer(localRoot string) http.Handler {
	root := filepath.Clean(strings.TrimSpace(localRoot))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet && r.Method != http.MethodHead {
			writeDerivedMediaError(w, r, http.StatusMethodNotAllowed, "method not allowed")
			return
		}
		rel := strings.TrimPrefix(r.URL.Path, "/media/")
		rel = strings.Trim(rel, "/")
		if rel == "" || strings.Contains(rel, "..") {
			writeDerivedMediaError(w, r, http.StatusBadRequest, "bad path")
			return
		}
		full := filepath.Join(root, filepath.FromSlash(rel))
		cleanRoot := root
		cleanFull := filepath.Clean(full)
		sep := string(filepath.Separator)
		if cleanFull != cleanRoot && !strings.HasPrefix(cleanFull, cleanRoot+sep) {
			writeDerivedMediaError(w, r, http.StatusBadRequest, "bad path")
			return
		}
		fi, err := os.Stat(cleanFull)
		if err != nil || fi.IsDir() {
			writeDerivedMediaError(w, r, http.StatusNotFound, "media not found")
			return
		}
		http.ServeFile(w, r, cleanFull)
	})
}

func writeDerivedMediaError(w http.ResponseWriter, r *http.Request, status int, debugMessage string) {
	kind := rterr.KindUser
	reason := "invalid_argument"
	userMessage := "媒体资源不可用"
	if status == http.StatusNotFound {
		reason = "not_found"
	}
	rterr.WriteHTTPError(
		w,
		rterr.NewAppError(
			rterr.NewCode(rterr.ModuleChat, kind, reason),
			userMessage,
			debugMessage,
		).WithLocation(rterr.RuntimeErrorLocation{
			BusinessObject: "chat_media",
			FunctionModule: "derived_media_file_server",
		}),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}

func applyEnvOverrides(cfg *config) {
	if v := os.Getenv("MONGO_URI"); v != "" {
		cfg.MongoDB.URI = v
	}
	if v := os.Getenv("MONGO_DATABASE"); v != "" {
		cfg.MongoDB.Database = v
	}

	applyRedisSceneEnv("CHAT_REDIS_REALTIME", &cfg.Redis.Realtime)
	applyRedisSceneEnv("CHAT_REDIS_GENERAL", &cfg.Redis.General)
	applyRedisSceneEnv("CHAT_REDIS_RELIABLE_TASK", &cfg.Redis.ReliableTask)

	if v := os.Getenv("REDIS_ADDR"); v != "" {
		if cfg.Redis.General.Addr == "" {
			cfg.Redis.General.Addr = v
		}
		if cfg.Redis.Realtime.Addr == "" {
			cfg.Redis.Realtime.Addr = v
		}
		if cfg.Redis.ReliableTask.Addr == "" {
			cfg.Redis.ReliableTask.Addr = v
		}
	}
	if v := os.Getenv("RELIABLE_TASK_READY_INDEX_ENABLED"); v == "true" || v == "1" {
		cfg.Runtime.ReliableTask.ReadyIndex.Enabled = true
	}
	if v := os.Getenv("RELIABLE_TASK_READY_INDEX_STREAM"); v != "" {
		cfg.Runtime.ReliableTask.ReadyIndex.Stream = v
	}
	if v := os.Getenv("RELIABLE_TASK_READY_INDEX_GROUP"); v != "" {
		cfg.Runtime.ReliableTask.ReadyIndex.Group = v
	}
	if v := os.Getenv("RELIABLE_TASK_READY_INDEX_QUEUE"); v != "" {
		cfg.Runtime.ReliableTask.ReadyIndex.Queue = v
	}
	if v := os.Getenv("CHAT_GROUP_AVATAR_CDN_BASE_URL"); v != "" {
		cfg.Runtime.Media.GroupAvatarCDNBaseURL = v
	}
	if v := os.Getenv("CHAT_GROUP_AVATAR_LOCAL_MEDIA_ROOT"); v != "" {
		cfg.Runtime.Media.GroupAvatarLocalMediaRoot = v
	}
	if v := os.Getenv("RUNTIME_SYNC_PATCH_TTL_HOURS"); v != "" {
		if hours, err := strconv.Atoi(v); err == nil {
			cfg.Runtime.Sync.PatchTTLHours = hours
		}
	}
}

func applyRedisSceneEnv(prefix string, cfg *redisSceneCfg) {
	if v := os.Getenv(prefix + "_MODE"); v != "" {
		cfg.Mode = v
	}
	if v := os.Getenv(prefix + "_ADDR"); v != "" {
		cfg.Addr = v
	}
	if v := os.Getenv(prefix + "_ADDRS"); v != "" {
		cfg.Addrs = strings.Split(v, ",")
	}
	if v := os.Getenv(prefix + "_PASSWORD"); v != "" {
		cfg.Password = v
	}
	if v := os.Getenv(prefix + "_TLS"); v == "true" || v == "1" {
		cfg.TLS = true
	}
}

func buildRedisRouter(cfg config) *rtredis.Router {
	routerCfg := rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"realtime":     toSceneConfig(cfg.Redis.Realtime),
			"general":      toSceneConfig(cfg.Redis.General),
			"rec":          toSceneConfig(cfg.Redis.General),
			"reliabletask": toSceneConfig(resolveReliableTaskRedisScene(cfg)),
		},
		PrefixRoutes: rtredis.DefaultRouterConfig().PrefixRoutes,
		DefaultScene: "general",
	}
	return platformredis.MustNewRouter(routerCfg)
}

func resolveReliableTaskRedisScene(cfg config) redisSceneCfg {
	scene := cfg.Redis.ReliableTask
	if strings.TrimSpace(scene.Mode) == "" &&
		strings.TrimSpace(scene.Addr) == "" &&
		len(scene.Addrs) == 0 {
		return cfg.Redis.General
	}
	return scene
}

func toSceneConfig(r redisSceneCfg) rtredis.SceneConfig {
	mode := strings.ToLower(strings.TrimSpace(r.Mode))
	if mode == "" {
		mode = "standalone"
	}
	if mode == "standalone" && r.Addr == "" {
		mode = "memory"
	}
	if mode == "cluster" && len(r.Addrs) == 0 {
		mode = "memory"
	}
	return rtredis.SceneConfig{
		Mode:         mode,
		Addr:         r.Addr,
		Addrs:        r.Addrs,
		Password:     r.Password,
		DB:           r.DB,
		TLS:          r.TLS,
		PoolSize:     r.Pool.Size,
		MinIdleConns: r.Pool.MinIdle,
	}
}
