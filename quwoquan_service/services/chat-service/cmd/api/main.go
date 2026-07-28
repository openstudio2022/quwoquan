package main

import (
	"context"
	"log"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	"quwoquan_service/generated/operationsecurity"
	rtmongo "quwoquan_service/internal/platform/mongodb"
	"quwoquan_service/internal/platform/reliabletaskmongo"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/controlplane"
	rterr "quwoquan_service/runtime/errors"
	rthealth "quwoquan_service/runtime/health"
	rtotel "quwoquan_service/runtime/otel"

	rtgov "quwoquan_service/runtime/governance"
	rthttp "quwoquan_service/runtime/http"
	runtimemedia "quwoquan_service/runtime/media"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	"quwoquan_service/runtime/reliabletask"
	runtimesync "quwoquan_service/runtime/sync"
	httpadapter "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/http"
	"quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/mq"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
	chatcache "quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/persistence"
	chatconfig "quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/runtimeconfig"
	messageexternal "quwoquan_service/services/chat-service/internal/chat/message/infrastructure/external"
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
		Auth struct {
			AccountSecurityAuthority struct {
				TimeoutMs int `yaml:"timeout_ms"`
			} `yaml:"account_security_authority"`
		} `yaml:"auth"`
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
	controlplane.StartReleaseConfigAttestation(
		serviceName, appEnv, configRoot, configVersion, imageVersion,
	)
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
	userServiceBaseURL, err := chatconfig.RequireInternalServiceBaseURL(
		"USER_SERVICE_BASE_URL",
		os.Getenv("USER_SERVICE_BASE_URL"),
	)
	if err != nil {
		log.Fatalf("chat-service user dependency invalid: %v", err)
	}
	accountSecurityAuthority, err := chatconfig.NewAccountSecurityAuthority(
		accessTokenConfig,
		userServiceBaseURL,
		cfg.Runtime.Auth.AccountSecurityAuthority.TimeoutMs,
	)
	if err != nil {
		log.Fatalf("chat-service account security authority invalid: %v", err)
	}
	circleServiceBaseURL := strings.TrimSpace(os.Getenv("CIRCLE_SERVICE_BASE_URL"))
	if circleServiceBaseURL == "" {
		circleServiceBaseURL = strings.TrimSpace(os.Getenv("GATEWAY_BASE_URL"))
	}
	circleServiceBaseURL, err = chatconfig.RequireInternalServiceBaseURL(
		"CIRCLE_SERVICE_BASE_URL or GATEWAY_BASE_URL",
		circleServiceBaseURL,
	)
	if err != nil {
		log.Fatalf("chat-service circle dependency invalid: %v", err)
	}
	contentServiceBaseURL, err := chatconfig.RequireInternalServiceBaseURL(
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
	messageTransport, err := requireChatMessageTransport(
		ctx,
		appEnv,
		router,
		map[string]string{
			"general":  cfg.Redis.General.Mode,
			"realtime": cfg.Redis.Realtime.Mode,
		},
	)
	if err != nil {
		log.Fatalf("chat-service message transport preflight failed: %v", err)
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
	circleGroupChatSyncFailures := persistence.NewMongoCircleGroupChatSyncFailureStore(mongoDB)
	if err := circleGroupChatSyncFailures.EnsureIndexes(ctx); err != nil {
		log.Fatalf("chat-service CircleGroup sync failure indexes unavailable: %v", err)
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
		Transactions:                      chatStore,
		Conversations:                     chatStore,
		CircleGroupConversations:          chatStore,
		Messages:                          chatStore,
		MessageProjection:                 chatStore,
		Members:                           chatStore,
		UserStates:                        chatStore,
		Receipts:                          chatStore,
		ConversationCommands:              conversationCommands,
		MembershipCommands:                membershipCommands,
		UserStateCommands:                 userStateCommands,
		CircleGroupMembershipProjections:  chatStore,
		CircleGroupChatBindingProjections: chatStore,
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
				cursor = application.EncodeMemberListNextCursorJoined(last.JoinedAt, last.ID)
			}
		},
	)
	eventPublisher := mq.NewEventPublisherWithTransport(
		messageTransport,
		recipientResolver,
	)
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
	circleGroupBindingOutboxRelay := application.NewAggregateOutboxRelay(
		conversationCommands,
		projectionCheckpoints,
		mq.NewCircleGroupConversationProvisionedStreamPublisher(router.Scene("general")),
		"chat-circle-group-conversation-binding-stream",
	)
	go func() {
		if err := circleGroupBindingOutboxRelay.Run(ctx, 100*time.Millisecond); err != nil {
			logger.Error("chat CircleGroup binding outbox relay stopped", "err", err)
		}
	}()
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
	relationshipCredentials, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		accessTokenConfig,
		"chat-service",
		[]string{"user.relationship.read"},
	)
	if err != nil {
		log.Fatalf("chat-service relationship credential init failed: %v", err)
	}
	relationshipGate, err := httpadapter.NewAuthorizedUserRelationshipGate(
		userServiceBaseURL,
		profileClient,
		relationshipCredentials,
	)
	if err != nil {
		log.Fatalf("chat-service relationship gate init failed: %v", err)
	}
	socialContactResolver, err := httpadapter.NewAuthorizedUserSocialContactResolver(
		userServiceBaseURL,
		profileClient,
		relationshipCredentials,
	)
	if err != nil {
		log.Fatalf("chat-service social contact resolver init failed: %v", err)
	}
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
	circleGroupChatSyncService := application.NewCircleGroupChatSyncService(
		conversationSvc,
		memberSvc,
	)
	circleGroupProvisioner, err := mq.NewCircleGroupChatSyncConsumer(
		router.Scene("general"),
		circleGroupChatSyncService,
		circleGroupChatSyncFailures,
		"chat-circle-group-provisioner:"+instanceID,
		logger,
		mq.DefaultCircleGroupProvisionerConsumerConfig(),
	)
	if err != nil {
		log.Fatalf("chat CircleGroup provisioner init failed: %v", err)
	}
	circleGroupMembershipProjector, err := mq.NewCircleGroupChatSyncConsumer(
		router.Scene("general"),
		circleGroupChatSyncService,
		circleGroupChatSyncFailures,
		"chat-circle-group-membership-projector:"+instanceID,
		logger,
		mq.DefaultCircleGroupMembershipConsumerConfig(),
	)
	if err != nil {
		log.Fatalf("chat CircleGroup membership projector init failed: %v", err)
	}
	for _, consumer := range []*mq.CircleGroupChatSyncConsumer{
		circleGroupProvisioner,
		circleGroupMembershipProjector,
	} {
		if err := consumer.EnsureGroup(ctx); err != nil {
			log.Fatalf("chat CircleGroup sync consumer group unavailable: %v", err)
		}
	}
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
	circleGroupSyncStopped := make(chan struct{}, 2)
	for _, consumer := range []*mq.CircleGroupChatSyncConsumer{
		circleGroupProvisioner,
		circleGroupMembershipProjector,
	} {
		go func(consumer *mq.CircleGroupChatSyncConsumer) {
			defer func() { circleGroupSyncStopped <- struct{}{} }()
			consumer.Run(ctx)
		}(consumer)
	}
	defer func() {
		cancelRuntime()
		select {
		case <-userAccountClosedStopped:
		case <-time.After(5 * time.Second):
			logger.Error("chat UserAccountClosed consumer shutdown timed out")
		}
		for range 2 {
			select {
			case <-circleGroupSyncStopped:
			case <-time.After(5 * time.Second):
				logger.Error("chat CircleGroup sync consumer shutdown timed out")
			}
		}
	}()
	healthChecker := rthealth.NewChecker()
	healthChecker.Register("redis", func(hctx context.Context) error {
		return router.PingAll(hctx)
	})
	healthChecker.Register("mongodb", func(hctx context.Context) error {
		return mongoClient.Ping(hctx, nil)
	})
	healthChecker.Register("account_security_authority", func(hctx context.Context) error {
		return accountSecurityAuthority.CheckAccountSecurityAuthority(hctx)
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
	healthChecker.Register("circle_group_conversation_binding_stream", func(context.Context) error {
		return circleGroupBindingOutboxRelay.Healthy(30 * time.Second)
	})
	healthChecker.Register("inbox_projection", func(context.Context) error {
		return inboxProjector.Healthy(5 * time.Second)
	})
	healthChecker.Register("user_account_closed_consumer", func(context.Context) error {
		return userAccountClosedConsumer.Healthy(15 * time.Second)
	})
	healthChecker.Register("circle_group_conversation_provisioner", func(context.Context) error {
		return circleGroupProvisioner.Healthy(30 * time.Second)
	})
	healthChecker.Register("circle_group_membership_projector", func(context.Context) error {
		return circleGroupMembershipProjector.Healthy(30 * time.Second)
	})

	chatHandler := httpadapter.NewChatHandler(
		conversationSvc,
		messageSvc,
		memberSvc,
		inboxSvc,
		userSyncService,
	)
	chatRoutes := chatHandler.Routes()
	internalChatRoutes := chatHandler.InternalRoutes()
	chatRoutes, err = runtimemessaging.WithDeadLetterRecoveryRoute(
		chatRoutes,
		runtimemessaging.DeadLetterRecoveryRouteConfig{
			Path:     "/internal/chat/account-closure/dead-letters:recover",
			Module:   rterr.ModuleChat,
			Releaser: userAccountClosedConsumer,
		},
	)
	if err != nil {
		log.Fatalf("chat account-closure recovery route failed: %v", err)
	}
	baseHandler := rtauth.RequireGeneratedOperationAuthorization(
		operationsecurity.ForDomain("chat"),
	)(chatRoutes)
	rootMux := http.NewServeMux()
	rootMux.HandleFunc("/healthz", healthChecker.Handler())
	rootMux.Handle("/metrics", rtmetrics.Handler())
	rootMux.Handle("/media/", newDerivedMediaFileServer(localMediaRoot))
	rootMux.Handle("/internal/chat/conversations/direct", internalChatRoutes)
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
			AccessTokenVerifier:      accessVerifier,
			AccountSecurityAuthority: accountSecurityAuthority,
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
