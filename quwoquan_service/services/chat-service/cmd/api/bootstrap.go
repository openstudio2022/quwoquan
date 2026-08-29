// Package bootstrap owns chat-service's private composition for servicekit.
package bootstrap

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"quwoquan_service/generated/operationsecurity"
	"quwoquan_service/internal/platform/reliabletaskmongo"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	rtgov "quwoquan_service/runtime/governance"
	runtimemedia "quwoquan_service/runtime/media"
	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/runtime/servicekit"
	runtimesync "quwoquan_service/runtime/sync"
	inboxhttp "quwoquan_service/services/chat-service/internal/chat/chat_inbox_view/adapters/inbound/http"
	inboxapp "quwoquan_service/services/chat-service/internal/chat/chat_inbox_view/application"
	inboxpersistence "quwoquan_service/services/chat-service/internal/chat/chat_inbox_view/infrastructure/persistence"
	httpadapter "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/http"
	"quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/mq"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
	chatcache "quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/persistence"
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

// NewModule assembles chat-service's private dependencies without binding a
// listener, accepting requests, starting workers, or owning process signals.
func NewModule() (*servicekit.Module, error) {
	return servicekit.Bootstrap(serviceName, servicekit.BootstrapSpec[config]{
		OperationDescriptors: operationsecurity.ForDomain("chat"),
		// 群头像等媒体面由浏览器直连，按 env 派生 origin 策略开跨域。
		CORS:            servicekit.BrowserCORSFromEnv(),
		AuthorityScopes: []string{"user.account.security.read"},
		// chat 不签发也不接受设备票据：不装配 verifier 后，带设备票据的
		// 请求由认证中间件 fail-closed 拒绝，与迁移前的中间件配置一致。
		SkipDeviceTicketAuth: true,
		SnapshotGuard:        snapshotGuard,
		ValidateConfig:       validateChatConfig,
		RedisScenes:          resolveRedisScenes,
		Assemble:             assembleChatDomain,
	})
}

func assembleChatDomain(asm *servicekit.Assembly, cfg *config) error {
	ctx := asm.Context
	logger := slog.Default()
	instanceID := asm.Identity.InstanceID
	accessTokenConfig := asm.Auth.AccessTokenConfig

	userServiceBaseURL, err := cfg.resolveUserServiceBaseURL()
	if err != nil {
		return err
	}
	circleServiceBaseURL, err := cfg.resolveCircleServiceBaseURL()
	if err != nil {
		return err
	}
	contentServiceBaseURL, err := cfg.resolveContentServiceBaseURL()
	if err != nil {
		return err
	}

	router := asm.RedisRouter
	// chat 的实时扇出、持久化事实流与可靠任务全部压在 Redis 上，任一 scene
	// 连不通都不该进入就绪，所以这里是 fail-closed 而不是告警降级。
	if err := router.PingAll(ctx); err != nil {
		return fmt.Errorf("redis dependency unavailable: %w", err)
	}
	messageTransport, realtimeResumeTransport, err := requireChatMessageTransport(
		ctx, asm.Identity.AppEnv, router, asm.RedisSceneModes,
	)
	if err != nil {
		return fmt.Errorf("message transport preflight failed: %w", err)
	}

	mongoDB, err := asm.Mongo(servicekit.MongoConfig{
		URI:      cfg.MongoDB.URI,
		Database: cfg.MongoDB.Database,
	})
	if err != nil {
		return err
	}
	chatStore := persistence.NewMongoChatStore(mongoDB)
	if err := chatStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("aggregate indexes unavailable: %w", err)
	}
	membershipStore := membershippersistence.NewMongoStore(mongoDB)
	if err := membershipStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("ConversationMembership indexes unavailable: %w", err)
	}
	userStateStore := userstatepersistence.NewMongoStore(mongoDB)
	if err := userStateStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("ConversationUserState indexes unavailable: %w", err)
	}
	inboxViewStore := inboxpersistence.NewMongoStore(mongoDB)
	if err := inboxViewStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("ChatInboxView indexes unavailable: %w", err)
	}
	receiptStore := receiptpersistence.NewMongoStore(mongoDB)
	if err := receiptStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("MessageReceiptFact indexes unavailable: %w", err)
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
			return fmt.Errorf("aggregate command indexes unavailable: %w", err)
		}
	}
	circleGroupChatSyncFailures := persistence.NewMongoCircleGroupChatSyncFailureStore(mongoDB)
	if err := circleGroupChatSyncFailures.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("CircleGroup sync failure indexes unavailable: %w", err)
	}
	userAccountClosedProjection := persistence.NewMongoUserAccountClosedProjection(
		mongoDB,
		router.Scene("general"),
	)
	if err := userAccountClosedProjection.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("UserAccountClosed indexes unavailable: %w", err)
	}
	userAccountRestrictionProjection, err :=
		persistence.NewMongoUserAccountRestrictionProjection(mongoDB)
	if err != nil {
		return fmt.Errorf("account restriction projection invalid: %w", err)
	}
	if err := userAccountRestrictionProjection.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("account restriction indexes unavailable: %w", err)
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
		return fmt.Errorf("UserAccountClosed consumer invalid: %w", err)
	}
	userAccountClosedConsumer.WithUserAccountRestrictionProjection(
		userAccountRestrictionProjection,
	)
	if err := userAccountClosedConsumer.EnsureGroup(ctx); err != nil {
		return fmt.Errorf("UserAccountClosed consumer group unavailable: %w", err)
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
	// 保留 relay 引用供 /readyz 与 Prometheus 检测停滞，而不是只在 goroutine
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
		return fmt.Errorf("default group avatar init failed: %w", err)
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
	reliableTaskCatalog, err := loadReliableTaskCatalog(asm.Identity.ConfigRoot)
	if err != nil {
		return fmt.Errorf("reliable task catalog load failed: %w", err)
	}
	reliableTaskStore := reliabletaskmongo.New(mongoDB)
	if err := reliableTaskStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("reliable task index init failed: %w", err)
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
			return fmt.Errorf("reliable task redis ready index init failed: %w", err)
		}
		if err := index.Ensure(ctx); err != nil {
			return fmt.Errorf("reliable task redis ready index ensure failed: %w", err)
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
		application.WithReliableGroupAvatarRuntimeIdentity(asm.Identity.AppEnv, instanceID),
		application.WithReliableGroupAvatarEnabledModules(resolveReliableTaskModules()),
		application.WithReliableGroupAvatarReadyIndex(reliableTaskReadyIndex),
	)
	profileCB := rtgov.NewCircuitBreaker(5, 15*time.Second, logger)
	profileClient := rtgov.WrapClientWithCB(&http.Client{Timeout: 2 * time.Second}, profileCB)
	profileResolver := httpadapter.NewUserProfileResolver(userServiceBaseURL, profileClient)
	relationshipCredentials, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		accessTokenConfig,
		serviceName,
		[]string{"user.relationship.read"},
	)
	if err != nil {
		return fmt.Errorf("relationship credential init failed: %w", err)
	}
	relationshipGate, err := httpadapter.NewAuthorizedUserRelationshipGate(
		userServiceBaseURL,
		profileClient,
		relationshipCredentials,
	)
	if err != nil {
		return fmt.Errorf("relationship gate init failed: %w", err)
	}
	socialContactResolver, err := httpadapter.NewAuthorizedUserSocialContactResolver(
		userServiceBaseURL,
		profileClient,
		relationshipCredentials,
	)
	if err != nil {
		return fmt.Errorf("social contact resolver init failed: %w", err)
	}
	circleListResolver := httpadapter.NewCircleListResolverClient(circleServiceBaseURL, profileClient)
	contentCredentials, err := asm.Auth.ServiceCredentials("content.media.delivery.read")
	if err != nil {
		return err
	}
	mediaAssetReader, err := messageexternal.NewMediaAssetDeliveryReader(
		contentServiceBaseURL,
		contentCredentials,
		nil,
	)
	if err != nil {
		return fmt.Errorf("content-service MediaAsset delivery reader invalid: %w", err)
	}
	intersectionCredentials, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		accessTokenConfig,
		serviceName,
		[]string{"content.my_intersections.read"},
	)
	if err != nil {
		return fmt.Errorf("content-service intersection credential init failed: %w", err)
	}
	contactIntersectionResolver, err := httpadapter.NewContactIntersectionResolverClient(
		contentServiceBaseURL,
		profileClient,
		intersectionCredentials,
	)
	if err != nil {
		return fmt.Errorf("content-service contact intersection reader invalid: %w", err)
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
		return fmt.Errorf("gathering icebreaker projector init failed: %w", err)
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
		return fmt.Errorf("chat CircleGroup provisioner init failed: %w", err)
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
		return fmt.Errorf("chat CircleGroup membership projector init failed: %w", err)
	}
	for _, consumer := range []*mq.CircleGroupChatSyncConsumer{
		circleGroupProvisioner,
		circleGroupMembershipProjector,
	} {
		if err := consumer.EnsureGroup(ctx); err != nil {
			return fmt.Errorf("chat CircleGroup sync consumer group unavailable: %w", err)
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

	// redis / mongodb / account_security_authority / config_sync 由骨架注册。
	asm.Health.Register("message_outbox_relay", func(context.Context) error {
		return messageOutboxRelay.Healthy(5 * time.Second)
	})
	for name, aggregateRelay := range aggregateOutboxRelays {
		relay := aggregateRelay
		asm.Health.Register(name, func(context.Context) error {
			return relay.Healthy(5 * time.Second)
		})
	}
	asm.Health.Register("circle_group_conversation_binding_stream", func(context.Context) error {
		return circleGroupBindingOutboxRelay.Healthy(30 * time.Second)
	})
	asm.Health.Register("inbox_projection", func(context.Context) error {
		return inboxViewProjector.Healthy(5 * time.Second)
	})
	asm.Health.Register("user_account_closed_consumer", func(context.Context) error {
		return userAccountClosedConsumer.Healthy(15 * time.Second)
	})
	asm.Health.Register("circle_group_conversation_provisioner", func(context.Context) error {
		return circleGroupProvisioner.Healthy(30 * time.Second)
	})
	asm.Health.Register("circle_group_membership_projector", func(context.Context) error {
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
	chatRoutes, err = runtimemessaging.WithDeadLetterRecoveryRoute(
		chatRoutes,
		runtimemessaging.DeadLetterRecoveryRouteConfig{
			Path:     "/internal/chat/account-closure/dead-letters:recover",
			Module:   rterr.ModuleChat,
			Releaser: userAccountClosedConsumer,
		},
	)
	if err != nil {
		return fmt.Errorf("chat account-closure recovery route failed: %w", err)
	}
	asm.Mux.Handle("/", chatRoutes)

	// 派生媒体分发、内部直连会话入口与运行时媒体指标不在 generated operation
	// contract 里，走不了 operation guard：它们各自在 handler 内收敛访问面
	// （路径遍历拒绝、服务间凭据、只读指标）。
	unguarded := asm.Unguarded()
	unguarded.Handle("/media/", newDerivedMediaFileServer(localMediaRoot))
	unguarded.Handle("/internal/chat/conversations/direct", chatHandler.InternalRoutes())
	unguarded.Handle("/metrics/runtime-media", application.NewRuntimeMediaMetricsHandler(
		groupAvatarScheduler,
		userSyncService,
		application.RuntimeMediaAlertThresholds{
			GroupAvatarRecomputeDurationMsP95: cfg.Runtime.Observability.RuntimeMedia.GroupAvatarRecomputeDurationMsP95,
			GroupAvatarFallbackRatio:          cfg.Runtime.Observability.RuntimeMedia.GroupAvatarFallbackRatio,
			HintToPullDelayMsP95:              cfg.Runtime.Observability.RuntimeMedia.HintToPullDelayMsP95,
			PatchFanoutFailureRatio:           cfg.Runtime.Observability.RuntimeMedia.PatchFanoutFailureRatio,
		},
	))

	registerChatWorkers(asm, chatWorkerSet{
		logger:                         logger,
		chatStorage:                    chatStorage,
		eventPublisher:                 eventPublisher,
		groupAvatarMedia:               groupAvatarMedia,
		userSyncService:                userSyncService,
		groupAvatarScheduler:           groupAvatarScheduler,
		messageOutboxRelay:             messageOutboxRelay,
		aggregateOutboxRelays:          aggregateOutboxRelays,
		circleGroupBindingOutboxRelay:  circleGroupBindingOutboxRelay,
		inboxViewProjector:             inboxViewProjector,
		rtcCallLogConsumer:             rtcCallLogConsumer,
		userAvatarConsumer:             userAvatarConsumer,
		userAccountClosedConsumer:      userAccountClosedConsumer,
		circleGroupProvisioner:         circleGroupProvisioner,
		circleGroupMembershipProjector: circleGroupMembershipProjector,
	})
	return nil
}

// chatWorkerSet 聚合需要长期运行的后台组件，避免 worker 注册段再展开一份
// 与装配段等长的参数列表。
type chatWorkerSet struct {
	logger                         *slog.Logger
	chatStorage                    application.ChatStoragePorts
	eventPublisher                 *mq.EventPublisher
	groupAvatarMedia               *runtimemedia.GroupAvatarService
	userSyncService                *runtimesync.Service
	groupAvatarScheduler           *application.ReliableGroupAvatarTaskScheduler
	messageOutboxRelay             *messageapp.MessageOutboxRelay
	aggregateOutboxRelays          map[string]*application.AggregateOutboxRelay
	circleGroupBindingOutboxRelay  *application.AggregateOutboxRelay
	inboxViewProjector             *inboxapp.ChatInboxViewProjector
	rtcCallLogConsumer             *mq.RtcCallEndedConsumer
	userAvatarConsumer             *mq.UserAvatarUpdateConsumer
	userAccountClosedConsumer      *mq.UserAccountClosedConsumer
	circleGroupProvisioner         *mq.CircleGroupChatSyncConsumer
	circleGroupMembershipProjector *mq.CircleGroupChatSyncConsumer
}

func registerChatWorkers(asm *servicekit.Assembly, set chatWorkerSet) {
	logger := set.logger
	asm.Workers.Add(func(workerCtx context.Context) {
		if err := set.messageOutboxRelay.Run(workerCtx, 100*time.Millisecond); err != nil && !errors.Is(err, context.Canceled) {
			logger.Error("chat message outbox relay stopped", "err", err)
		}
	})
	asm.Workers.Add(func(workerCtx context.Context) {
		if err := set.circleGroupBindingOutboxRelay.Run(workerCtx, 100*time.Millisecond); err != nil && !errors.Is(err, context.Canceled) {
			logger.Error("chat CircleGroup binding outbox relay stopped", "err", err)
		}
	})
	asm.Workers.Add(func(workerCtx context.Context) {
		if err := set.inboxViewProjector.Run(workerCtx, 200*time.Millisecond); err != nil && !errors.Is(err, context.Canceled) {
			logger.Error("ChatInboxView projector stopped", "err", err)
		}
	})
	asm.Workers.Add(func(workerCtx context.Context) {
		if err := application.BackfillMissingGroupAvatars(
			workerCtx,
			set.chatStorage,
			set.eventPublisher,
			set.groupAvatarMedia,
			set.userSyncService,
			set.groupAvatarScheduler,
			200,
		); err != nil && !errors.Is(err, context.Canceled) {
			logger.Error("chat-service group avatar backfill failed", "err", err)
		}
	})
	asm.Workers.Add(func(workerCtx context.Context) {
		runRTCCallLogConsumer(workerCtx, set.rtcCallLogConsumer, logger)
	})
	asm.Workers.Add(func(workerCtx context.Context) {
		if err := set.userAvatarConsumer.Run(workerCtx); err != nil && !errors.Is(err, context.Canceled) {
			logger.Error("chat user avatar consumer stopped", "err", err)
		}
	})
	asm.Workers.Add(set.userAccountClosedConsumer.Run)
	asm.Workers.Add(set.circleGroupProvisioner.Run)
	asm.Workers.Add(set.circleGroupMembershipProjector.Run)
	for name, relay := range set.aggregateOutboxRelays {
		name, relay := name, relay
		asm.Workers.Add(func(workerCtx context.Context) {
			if err := relay.Run(workerCtx, 100*time.Millisecond); err != nil && !errors.Is(err, context.Canceled) {
				logger.Error("chat aggregate outbox relay stopped", "consumer", name, "err", err)
			}
		})
	}

	// 调度器的 Start 可失败，用 AddFallible 让失败停在 Start 相位：进程既不
	// 进入就绪窗口也不开放 admission，与迁移前 Module.Start 直接返回错误等价。
	asm.Workers.AddFallible("group_avatar_scheduler", func(workerCtx context.Context) error {
		if err := set.groupAvatarScheduler.Start(workerCtx); err != nil {
			return fmt.Errorf("reliable task scheduler start: %w", err)
		}
		return nil
	})
	// 排空在独立 worker 里等待：Start 成功后调度器已在内部 goroutine 运行，
	// WaitForStop 会阻塞到 context 取消，不能放在 Start 相位。
	asm.Workers.Add(func(workerCtx context.Context) {
		if err := set.groupAvatarScheduler.WaitForStop(workerCtx); err != nil &&
			!errors.Is(err, context.Canceled) {
			logger.Error("chat group avatar scheduler drain failed", "err", err)
		}
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
