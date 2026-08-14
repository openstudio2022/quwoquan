// Package bootstrap owns chat-service's private composition for servicehost.
package bootstrap

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"strings"
	"sync"
	"sync/atomic"
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
	"quwoquan_service/runtime/servicehost"
	runtimesync "quwoquan_service/runtime/sync"
	inboxhttp "quwoquan_service/services/chat-service/internal/chat/chat_inbox_view/adapters/inbound/http"
	inboxapp "quwoquan_service/services/chat-service/internal/chat/chat_inbox_view/application"
	inboxpersistence "quwoquan_service/services/chat-service/internal/chat/chat_inbox_view/infrastructure/persistence"
	httpadapter "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/http"
	"quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/mq"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
	chatcache "quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/persistence"
	chatconfig "quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/runtimeconfig"
	membershiphttp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/adapters/inbound/http"
	membershipapp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/application"
	membershippersistence "quwoquan_service/services/chat-service/internal/chat/conversation_membership/infrastructure/persistence"
	userstatehttp "quwoquan_service/services/chat-service/internal/chat/conversation_user_state/adapters/inbound/http"
	userstatepersistence "quwoquan_service/services/chat-service/internal/chat/conversation_user_state/infrastructure/persistence"
	messagehttp "quwoquan_service/services/chat-service/internal/chat/message/adapters/inbound/http"
	messageapp "quwoquan_service/services/chat-service/internal/chat/message/application"
	messageexternal "quwoquan_service/services/chat-service/internal/chat/message/infrastructure/external"
	receipthttp "quwoquan_service/services/chat-service/internal/chat/message_receipt_fact/adapters/inbound/http"
	receiptapp "quwoquan_service/services/chat-service/internal/chat/message_receipt_fact/application"
	receiptpersistence "quwoquan_service/services/chat-service/internal/chat/message_receipt_fact/infrastructure/persistence"
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
		Version string `yaml:"version"`
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

// Module keeps chat-service's HTTP contract and private workers together while
// servicehost owns process-level listener, admission and shutdown sequencing.
type Module struct {
	configDigest string
	server       *http.Server
	health       *rthealth.Checker
	listener     net.Listener
	admission    atomic.Bool
	serveError   chan error

	workerCancel context.CancelFunc
	workerGroup  sync.WaitGroup
	workerStart  []func(context.Context)
	runContext   context.Context

	startManagedWorker func(context.Context) error
	waitManagedWorker  func(context.Context) error
	cleanup            func()
}

var _ servicehost.Module = (*Module)(nil)

func chainCleanup(previous func(), action func()) func() {
	return func() {
		action()
		previous()
	}
}

// NewModule assembles chat-service's private dependencies without binding a
// listener, accepting requests, starting workers, or owning process signals.
func NewModule() (_ *Module, resultErr error) {
	cleanup := func() {}
	initialized := false
	defer func() {
		if !initialized {
			cleanup()
		}
	}()

	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		return nil, fmt.Errorf("chat-service runtime identity invalid: %w", err)
	}

	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		return nil, fmt.Errorf("chat-service config load failed: %w", err)
	}
	applyEnvOverrides(&cfg)
	if err := validateRuntimeConfigurationIdentity(cfg, configVersion); err != nil {
		return nil, fmt.Errorf("chat-service config identity failed: %w", err)
	}
	controlplane.StartReleaseConfigAttestation(
		serviceName, appEnv, configRoot, configVersion, imageVersion,
	)
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		return nil, fmt.Errorf("chat-service access token config invalid: %w", err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		return nil, fmt.Errorf("chat-service access token verifier invalid: %w", err)
	}
	addr := getenvOrDefault("CHAT_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18081"
	}

	logger := slog.Default()
	instanceID := strings.TrimSpace(
		servicehost.ModuleEnvironmentValue("chat-service", "SERVICE_INSTANCE_ID"),
	)
	if instanceID == "" {
		instanceID = hostname()
	}
	userServiceBaseURL, err := chatconfig.RequireInternalServiceBaseURL(
		"USER_SERVICE_BASE_URL",
		os.Getenv("USER_SERVICE_BASE_URL"),
	)
	if err != nil {
		return nil, fmt.Errorf("chat-service user dependency invalid: %w", err)
	}
	accountSecurityAuthority, err := chatconfig.NewAccountSecurityAuthority(
		accessTokenConfig,
		userServiceBaseURL,
		cfg.Runtime.Auth.AccountSecurityAuthority.TimeoutMs,
	)
	if err != nil {
		return nil, fmt.Errorf("chat-service account security authority invalid: %w", err)
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
		return nil, fmt.Errorf("chat-service circle dependency invalid: %w", err)
	}
	contentServiceBaseURL, err := chatconfig.RequireInternalServiceBaseURL(
		"CONTENT_SERVICE_BASE_URL",
		os.Getenv("CONTENT_SERVICE_BASE_URL"),
	)
	if err != nil {
		return nil, fmt.Errorf("chat-service content dependency invalid: %w", err)
	}

	// 服务日志上云：stdout/stderr 镜像推送到 Product Ops 内部 runtime log
	// ingest（机器凭据）；未配置时仅 stdout，推送失败静默降级。
	runtimeLogExporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		return nil, fmt.Errorf("chat-service runtime log exporter init failed: %w", err)
	}
	cleanup = chainCleanup(cleanup, func() {
		runtimeLogExporter.Close()
	})
	standardLogWriter := robs.NewRuntimeLogExportWriter(os.Stdout, 512, runtimeLogExporter.Export)
	errorLogWriter := robs.NewRuntimeLogExportWriter(os.Stderr, 512, runtimeLogExporter.Export)
	cleanup = chainCleanup(cleanup, func() {
		errorLogWriter.Close()
		standardLogWriter.Close()
	})
	ioLogger := robs.NewIOAccessLogger(standardLogWriter)
	processLogger, err := robs.NewProcessTraceLogger(standardLogWriter, errorLogWriter, "info", nil)
	if err != nil {
		return nil, fmt.Errorf("chat-service process logger init failed: %w", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(standardLogWriter, errorLogWriter, nil)
	if err != nil {
		return nil, fmt.Errorf("chat-service exception logger init failed: %w", err)
	}

	router := buildRedisRouter(cfg)
	cleanup = chainCleanup(cleanup, func() {
		_ = router.Close()
	})

	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "chat-service", SamplingRatio: 0.1})
	cleanup = chainCleanup(cleanup, func() {
		otelShutdown()
	})

	ctx := context.Background()

	if err := router.PingAll(ctx); err != nil {
		return nil, fmt.Errorf("chat-service redis dependency unavailable: %w", err)
	}
	messageTransport, realtimeResumeTransport, err := requireChatMessageTransport(
		ctx,
		appEnv,
		router,
		map[string]string{
			"general":  cfg.Redis.General.Mode,
			"realtime": cfg.Redis.Realtime.Mode,
		},
	)
	if err != nil {
		return nil, fmt.Errorf("chat-service message transport preflight failed: %w", err)
	}
	mongoClient := rtmongo.MustConnect(ctx, rtmongo.ConnectConfig{URI: cfg.MongoDB.URI}, "chat-service")
	cleanup = chainCleanup(cleanup, func() {
		disconnectCtx, cancelDisconnect := context.WithTimeout(
			context.Background(),
			5*time.Second,
		)
		defer cancelDisconnect()
		_ = mongoClient.Disconnect(disconnectCtx)
	})

	mongoDB := mongoClient.Database(cfg.MongoDB.Database)
	chatStore := persistence.NewMongoChatStore(mongoDB)
	if err := chatStore.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("chat-service aggregate indexes unavailable: %w", err)
	}
	membershipStore := membershippersistence.NewMongoStore(mongoDB)
	if err := membershipStore.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("chat-service ConversationMembership indexes unavailable: %w", err)
	}
	userStateStore := userstatepersistence.NewMongoStore(mongoDB)
	if err := userStateStore.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("chat-service ConversationUserState indexes unavailable: %w", err)
	}
	inboxViewStore := inboxpersistence.NewMongoStore(mongoDB)
	if err := inboxViewStore.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("chat-service ChatInboxView indexes unavailable: %w", err)
	}
	receiptStore := receiptpersistence.NewMongoStore(mongoDB)
	if err := receiptStore.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("chat-service MessageReceiptFact indexes unavailable: %w", err)
	}
	receiptFacts := receiptapp.NewAppender(receiptStore)
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
			return nil, fmt.Errorf("chat-service aggregate command indexes unavailable: %w", err)
		}
	}
	circleGroupChatSyncFailures := persistence.NewMongoCircleGroupChatSyncFailureStore(mongoDB)
	if err := circleGroupChatSyncFailures.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("chat-service CircleGroup sync failure indexes unavailable: %w", err)
	}
	userAccountClosedProjection := persistence.NewMongoUserAccountClosedProjection(
		mongoDB,
		router.Scene("general"),
	)
	if err := userAccountClosedProjection.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("chat-service UserAccountClosed indexes unavailable: %w", err)
	}
	userAccountRestrictionProjection, err :=
		persistence.NewMongoUserAccountRestrictionProjection(mongoDB)
	if err != nil {
		return nil, fmt.Errorf("chat-service account restriction projection invalid: %w", err)
	}
	if err := userAccountRestrictionProjection.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("chat-service account restriction indexes unavailable: %w", err)
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
		return nil, fmt.Errorf("chat-service UserAccountClosed consumer invalid: %w", err)
	}
	userAccountClosedConsumer.WithUserAccountRestrictionProjection(
		userAccountRestrictionProjection,
	)
	if err := userAccountClosedConsumer.EnsureGroup(ctx); err != nil {
		return nil, fmt.Errorf("chat-service UserAccountClosed consumer group unavailable: %w", err)
	}
	projectionCheckpoints := persistence.NewMongoProjectionCheckpointStore(mongoDB)
	chatStorage := application.ChatStoragePorts{
		Transactions:                      chatStore,
		Conversations:                     chatStore,
		CircleGroupConversations:          chatStore,
		GatheringConversations:            chatStore,
		Messages:                          chatStore,
		MessageProjection:                 chatStore,
		Members:                           membershipStore,
		RosterProjection:                  chatStore,
		UserStates:                        userStateStore,
		ReceiptFacts:                      receiptFacts,
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
				members, err := membershipStore.ListMembers(
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
	eventPublisher := mq.NewEventPublisherWithTransports(
		messageTransport,
		realtimeResumeTransport,
		recipientResolver,
	)
	messageOutboxRelay := messageapp.NewMessageOutboxRelay(
		chatStore,
		chatStore,
		chatStore,
		eventPublisher,
		"chat-runtime-fanout",
	)
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
	}
	circleGroupBindingOutboxRelay := application.NewAggregateOutboxRelay(
		conversationCommands,
		projectionCheckpoints,
		mq.NewCircleGroupConversationProvisionedStreamPublisher(router.Scene("general")),
		"chat-circle-group-conversation-binding-stream",
	)
	// ChatInboxView 是唯一收件箱读模型：以四个对象 outbox 各自的
	// checkpoint 驱动，先单调推进 ConversationUserState，再原子刷新物化行。
	inboxViewProjector := inboxapp.NewProjector(
		inboxViewStore,
		inboxViewStore,
		chatInboxSnapshotSource{
			conversations: chatStore,
			states:        userStateStore,
			members:       membershipStore,
		},
		chatInboxMembershipReader{store: membershipStore},
		chatInboxStateAdvancer{store: userStateStore},
		map[string]inboxapp.EventSource{
			"message":      chatInboxMessageEventSource{source: chatStore},
			"conversation": chatInboxAggregateEventSource{source: conversationCommands},
			"membership":   chatInboxAggregateEventSource{source: membershipCommands},
			"user_state":   chatInboxAggregateEventSource{source: userStateCommands},
		},
	)
	localMediaRoot := strings.TrimSpace(cfg.Runtime.Media.GroupAvatarLocalMediaRoot)
	if localMediaRoot == "" {
		localMediaRoot = "./var/chat-media"
	}
	application.ConfigureGroupAvatarCDNBase(cfg.Runtime.Media.GroupAvatarCDNBaseURL)
	if err := runtimemedia.EnsureDefaultGroupAvatarFile(localMediaRoot); err != nil {
		return nil, fmt.Errorf("chat-service default group avatar init failed: %w", err)
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
		return nil, fmt.Errorf("chat-service reliable task catalog load failed: %w", err)
	}
	reliableTaskStore := reliabletaskmongo.New(mongoDB)
	if err := reliableTaskStore.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("chat-service reliable task index init failed: %w", err)
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
			return nil, fmt.Errorf("chat-service reliable task redis ready index init failed: %w", err)
		}
		if err := index.Ensure(ctx); err != nil {
			return nil, fmt.Errorf("chat-service reliable task redis ready index ensure failed: %w", err)
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
	profileCB := rtgov.NewCircuitBreaker(5, 15*time.Second, slog.Default())
	profileClient := rtgov.WrapClientWithCB(&http.Client{Timeout: 2 * time.Second}, profileCB)
	profileResolver := httpadapter.NewUserProfileResolver(userServiceBaseURL, profileClient)
	relationshipCredentials, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		accessTokenConfig,
		"chat-service",
		[]string{"user.relationship.read"},
	)
	if err != nil {
		return nil, fmt.Errorf("chat-service relationship credential init failed: %w", err)
	}
	relationshipGate, err := httpadapter.NewAuthorizedUserRelationshipGate(
		userServiceBaseURL,
		profileClient,
		relationshipCredentials,
	)
	if err != nil {
		return nil, fmt.Errorf("chat-service relationship gate init failed: %w", err)
	}
	socialContactResolver, err := httpadapter.NewAuthorizedUserSocialContactResolver(
		userServiceBaseURL,
		profileClient,
		relationshipCredentials,
	)
	if err != nil {
		return nil, fmt.Errorf("chat-service social contact resolver init failed: %w", err)
	}
	circleListResolver := httpadapter.NewCircleListResolverClient(circleServiceBaseURL, profileClient)
	contentCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"chat-service",
		[]string{"content.media.delivery.read"},
	)
	if err != nil {
		return nil, fmt.Errorf("content-service delivery credential init failed: %w", err)
	}
	mediaAssetReader, err := messageexternal.NewMediaAssetDeliveryReader(
		contentServiceBaseURL,
		contentCredentials,
		nil,
	)
	if err != nil {
		return nil, fmt.Errorf("content-service MediaAsset delivery reader invalid: %w", err)
	}
	intersectionCredentials, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		accessTokenConfig,
		"chat-service",
		[]string{"content.my_intersections.read"},
	)
	if err != nil {
		return nil, fmt.Errorf("content-service intersection credential init failed: %w", err)
	}
	contactIntersectionResolver, err := httpadapter.NewContactIntersectionResolverClient(
		contentServiceBaseURL,
		profileClient,
		intersectionCredentials,
	)
	if err != nil {
		return nil, fmt.Errorf("content-service contact intersection reader invalid: %w", err)
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
	rtcCallLogHandler := messageapp.NewRtcCallLogHandler(
		rtcCallLogProjectionBackend{writer: messageSvc},
	)
	rtcCallLogConsumer := mq.NewRtcCallEndedConsumer(
		router.Scene("realtime"),
		rtcCallLogConsumerWriter{handler: rtcCallLogHandler},
		instanceID,
	)
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
		application.WithContactIntersectionResolver(contactIntersectionResolver),
	)
	gatheringIcebreaker, err := application.NewGatheringIcebreakerProjector(
		messageSvc,
		contactIntersectionResolver,
		logger,
	)
	if err != nil {
		return nil, fmt.Errorf("gathering icebreaker projector init failed: %w", err)
	}
	gatheringMembershipProjection := membershipapp.NewGatheringProjectionFacade(
		chatStore,
		gatheringBindingReader{reader: chatStore},
		membershipStore,
		gatheringUserStateWriter{states: userStateStore},
		gatheringRosterWriter{roster: chatStore},
		gatheringProfileReader{profiles: profileResolver},
		membershipStore,
		gatheringProjectionOutbox{members: membershipCommands, conversations: conversationCommands},
	).WithGatheringMemberJoinedHook(gatheringIcebreaker)
	circleGroupChatSyncService := application.NewCircleGroupConversationProjectionHandler(
		conversationSvc,
		memberSvc,
	)
	circleGroupMembershipHandler := membershipapp.NewCircleGroupMembershipProjectionHandler(
		circleGroupMembershipProjectionBackend{projector: circleGroupChatSyncService},
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
		return nil, fmt.Errorf("chat CircleGroup provisioner init failed: %w", err)
	}
	circleGroupMembershipProjector, err := mq.NewCircleGroupChatSyncConsumer(
		router.Scene("general"),
		circleGroupMembershipConsumerProjector{handler: circleGroupMembershipHandler},
		circleGroupChatSyncFailures,
		"chat-circle-group-membership-projector:"+instanceID,
		logger,
		mq.DefaultCircleGroupMembershipConsumerConfig(),
	)
	if err != nil {
		return nil, fmt.Errorf("chat CircleGroup membership projector init failed: %w", err)
	}
	for _, consumer := range []*mq.CircleGroupChatSyncConsumer{
		circleGroupProvisioner,
		circleGroupMembershipProjector,
	} {
		if err := consumer.EnsureGroup(ctx); err != nil {
			return nil, fmt.Errorf("chat CircleGroup sync consumer group unavailable: %w", err)
		}
	}
	inboxSvc := application.NewInboxService(chatInboxConversationReader{
		reader: inboxapp.NewReader(inboxViewStore),
	})
	userAvatarConsumer := mq.NewUserAvatarUpdateConsumer(
		router.Scene("general"),
		chatStorage,
		eventPublisher,
		groupAvatarMedia,
		userSyncService,
		groupAvatarScheduler,
		logger,
	)
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
		return inboxViewProjector.Healthy(5 * time.Second)
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
	chatObjectRoutes := http.NewServeMux()
	inboxhttp.NewHandler(inboxViewStore).Register(chatObjectRoutes)
	membershiphttp.NewHandler(memberSvc).Register(chatObjectRoutes)
	membershiphttp.NewGatheringProjectionHandler(gatheringMembershipProjection).Register(chatObjectRoutes)
	userstatehttp.NewHandler(messageSvc, conversationSvc).Register(chatObjectRoutes)
	messagehttp.NewHandler(messageSvc).Register(chatObjectRoutes)
	messageReceiptHandler := receipthttp.NewHandler(messageSvc)
	chatObjectRoutes.HandleFunc(
		"GET /chat/conversations/{conversationId}/messages/{messageId}/receipts",
		messageReceiptHandler.GetReceipts,
	)
	chatHandler.RegisterRoutes(chatObjectRoutes)
	var chatRoutes http.Handler = chatObjectRoutes
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
		return nil, fmt.Errorf("chat account-closure recovery route failed: %w", err)
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

	timeouts := rtauth.ContractHTTPServerTimeouts(
		operationsecurity.ForDomain("chat"),
	)
	server := &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:      accessVerifier,
			AccountSecurityAuthority: accountSecurityAuthority,
		})(corsHandler),
		ReadHeaderTimeout: timeouts.ReadHeader,
		WriteTimeout:      timeouts.Write,
		IdleTimeout:       timeouts.Idle,
	}

	workerStart := []func(context.Context){
		func(workerCtx context.Context) {
			if err := messageOutboxRelay.Run(workerCtx, 100*time.Millisecond); err != nil && !errors.Is(err, context.Canceled) {
				logger.Error("chat message outbox relay stopped", "err", err)
			}
		},
		func(workerCtx context.Context) {
			if err := circleGroupBindingOutboxRelay.Run(workerCtx, 100*time.Millisecond); err != nil && !errors.Is(err, context.Canceled) {
				logger.Error("chat CircleGroup binding outbox relay stopped", "err", err)
			}
		},
		func(workerCtx context.Context) {
			if err := inboxViewProjector.Run(workerCtx, 200*time.Millisecond); err != nil && !errors.Is(err, context.Canceled) {
				logger.Error("ChatInboxView projector stopped", "err", err)
			}
		},
		func(workerCtx context.Context) {
			if err := application.BackfillMissingGroupAvatars(
				workerCtx,
				chatStorage,
				eventPublisher,
				groupAvatarMedia,
				userSyncService,
				groupAvatarScheduler,
				200,
			); err != nil && !errors.Is(err, context.Canceled) {
				logger.Error("chat-service group avatar backfill failed", "err", err)
			}
		},
		func(workerCtx context.Context) {
			runRTCCallLogConsumer(workerCtx, rtcCallLogConsumer, logger)
		},
		func(workerCtx context.Context) {
			if err := userAvatarConsumer.Run(workerCtx); err != nil && !errors.Is(err, context.Canceled) {
				logger.Error("chat user avatar consumer stopped", "err", err)
			}
		},
		userAccountClosedConsumer.Run,
		circleGroupProvisioner.Run,
		circleGroupMembershipProjector.Run,
	}
	for name, relay := range aggregateOutboxRelays {
		name, relay := name, relay
		workerStart = append(workerStart, func(workerCtx context.Context) {
			if err := relay.Run(workerCtx, 100*time.Millisecond); err != nil && !errors.Is(err, context.Canceled) {
				logger.Error("chat aggregate outbox relay stopped", "consumer", name, "err", err)
			}
		})
	}

	module := &Module{
		configDigest:       configVersion,
		server:             server,
		health:             healthChecker,
		serveError:         make(chan error, 1),
		workerStart:        workerStart,
		startManagedWorker: groupAvatarScheduler.Start,
		waitManagedWorker:  groupAvatarScheduler.WaitForStop,
		cleanup:            cleanup,
	}
	if module.configDigest == "" {
		module.configDigest = cfg.Config.Version
	}
	if module.configDigest == "" {
		module.configDigest = operationsecurity.ContractGraphSHA256
	}
	server.Handler = module.admissionHandler(server.Handler)
	server.BaseContext = func(net.Listener) context.Context {
		if module.runContext != nil {
			return module.runContext
		}
		return context.Background()
	}
	initialized = true
	return module, nil
}

func (module *Module) Name() string { return "chat-service" }

func (module *Module) ConfigDigest() string {
	if module == nil {
		return ""
	}
	return module.configDigest
}

func (module *Module) ValidateConfig(context.Context) error {
	if module == nil || module.server == nil || module.health == nil || module.cleanup == nil || len(module.workerStart) == 0 {
		return errors.New("chat-service module is incomplete")
	}
	return nil
}

func (module *Module) PrepareMigration(context.Context) error {
	return nil
}

func (module *Module) Bind(context.Context) error {
	if module == nil || module.server == nil {
		return errors.New("chat-service HTTP server is unavailable")
	}
	listener, err := net.Listen("tcp", module.server.Addr)
	if err != nil {
		return fmt.Errorf("chat-service listener bind: %w", err)
	}
	module.listener = listener
	return nil
}

func (module *Module) Start(ctx context.Context) error {
	if module == nil || module.listener == nil {
		return errors.New("chat-service listener is not bound")
	}
	module.runContext, module.workerCancel = context.WithCancel(ctx)
	if module.startManagedWorker != nil {
		if err := module.startManagedWorker(module.runContext); err != nil {
			module.workerCancel()
			return fmt.Errorf("chat-service reliable task scheduler start: %w", err)
		}
	}
	for _, start := range module.workerStart {
		module.workerGroup.Add(1)
		module.startWorker(start)
	}
	module.workerGroup.Add(1)
	go func() {
		defer module.workerGroup.Done()
		if err := module.server.Serve(module.listener); err != nil && !errors.Is(err, http.ErrServerClosed) {
			select {
			case module.serveError <- err:
			case <-module.runContext.Done():
			}
		}
	}()
	return nil
}

func (module *Module) Ready(ctx context.Context) error {
	if result := module.health.Check(ctx); result.Status != "ok" {
		return fmt.Errorf("chat-service readiness failed: %v", result.FailedChecks)
	}
	select {
	case err := <-module.serveError:
		return fmt.Errorf("chat-service listener failed: %w", err)
	default:
		return nil
	}
}

func (module *Module) OpenAdmission(context.Context) error {
	module.admission.Store(true)
	return nil
}

func (module *Module) Shutdown(ctx context.Context) error {
	module.admission.Store(false)
	if module.workerCancel != nil {
		module.workerCancel()
		module.workerCancel = nil
	}

	var result error
	if module.server != nil {
		result = errors.Join(result, module.server.Shutdown(ctx))
	}
	result = errors.Join(result, module.waitForWorkers(ctx))
	if module.waitManagedWorker != nil {
		result = errors.Join(result, module.waitManagedWorker(ctx))
	}
	if module.cleanup != nil {
		module.cleanup()
		module.cleanup = nil
	}
	return result
}

func (module *Module) startWorker(start func(context.Context)) {
	go func() {
		defer module.workerGroup.Done()
		start(module.runContext)
	}()
}

func (module *Module) waitForWorkers(ctx context.Context) error {
	done := make(chan struct{})
	go func() {
		module.workerGroup.Wait()
		close(done)
	}()
	select {
	case <-done:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (module *Module) admissionHandler(next http.Handler) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		switch request.URL.Path {
		case "/healthz", "/metrics":
			next.ServeHTTP(writer, request)
			return
		}
		if !module.admission.Load() {
			rterr.WriteHTTPError(
				writer,
				rterr.NewAppError(
					rterr.NewCode(rterr.ModuleGateway, rterr.KindMiddleware, "upstream_unavailable"),
					"服务暂不可用，请稍后重试",
					"service admission is not ready",
				).WithMetadata("upstream_unavailable", http.StatusServiceUnavailable).
					WithRecoveryDirective("retry", "snackbar", 1),
				rterr.HTTPWriteOptionsFromRequest(request),
			)
			return
		}
		next.ServeHTTP(writer, request)
	})
}

func runRTCCallLogConsumer(
	ctx context.Context,
	consumer *mq.RtcCallEndedConsumer,
	logger *slog.Logger,
) {
	for {
		if err := consumer.Run(ctx); err != nil {
			if ctx.Err() != nil {
				return
			}
			logger.Error("chat rtc CallEnded consumer stopped", "error", err)
			retry := time.NewTimer(time.Second)
			select {
			case <-ctx.Done():
				retry.Stop()
				return
			case <-retry.C:
				continue
			}
		}
		return
	}
}
