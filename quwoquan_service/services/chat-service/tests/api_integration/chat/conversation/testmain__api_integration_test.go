package api_integration

import (
	"bytes"
	"context"
	"fmt"
	"image"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/reliabletaskmongo"
	"quwoquan_service/internal/platform/testinfra"
	runtimemedia "quwoquan_service/runtime/media"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/reliabletask"
	runtimesync "quwoquan_service/runtime/sync"
	inboxhttp "quwoquan_service/services/chat-service/internal/chat/chat_inbox_view/adapters/inbound/http"
	inboxapp "quwoquan_service/services/chat-service/internal/chat/chat_inbox_view/application"
	inboxpersistence "quwoquan_service/services/chat-service/internal/chat/chat_inbox_view/infrastructure/persistence"
	chathttp "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/http"
	"quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/mq"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
	chatcache "quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/persistence"
	membershiphttp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/adapters/inbound/http"
	membershippersistence "quwoquan_service/services/chat-service/internal/chat/conversation_membership/infrastructure/persistence"
	userstatehttp "quwoquan_service/services/chat-service/internal/chat/conversation_user_state/adapters/inbound/http"
	userstatepersistence "quwoquan_service/services/chat-service/internal/chat/conversation_user_state/infrastructure/persistence"
	messagehttp "quwoquan_service/services/chat-service/internal/chat/message/adapters/inbound/http"
	messageports "quwoquan_service/services/chat-service/internal/chat/message/domain/ports"
	receipthttp "quwoquan_service/services/chat-service/internal/chat/message_receipt_fact/adapters/inbound/http"
	receiptpersistence "quwoquan_service/services/chat-service/internal/chat/message_receipt_fact/infrastructure/persistence"
)

var (
	testHandler                http.Handler
	testChatMediaRoot          string
	mongoDB                    *mongo.Database
	mongoClient                *mongo.Client
	integrationRedis           *testinfra.RealRedis
	redisRouter                *rtredis.Router
	testEventPublisher         application.EventPublisher
	testMessageOutboxRelay     *application.MessageOutboxRelay
	testMessageService         *application.MessageService
	testAggregateOutboxRelays  []*application.AggregateOutboxRelay
	testInboxViewProjector     *inboxapp.Projector
	testInboxViewStore         *inboxpersistence.MongoStore
	testGroupAvatarMedia       application.GroupAvatarAssetizer
	testUserSyncPublisher      application.UserSyncPublisher
	testGroupAvatarScheduler   *application.ReliableGroupAvatarTaskScheduler
	relationshipContractServer *httptest.Server
	testRelationshipGate       application.RelationshipGate
)

var collections = []string{
	"conversations",
	"conversations_command_receipts",
	"conversations_outbox",
	"messages",
	"messages_sequences",
	"messages_command_receipts",
	"messages_outbox",
	"messages_outbox_sequences",
	"messages_projection_checkpoints",
	"conversation_memberships",
	"conversation_memberships_command_receipts",
	"conversation_memberships_outbox",
	"conversation_user_states",
	"conversation_user_states_command_receipts",
	"conversation_user_states_outbox",
	"chat_aggregate_outbox_sequences",
	"chat_projection_checkpoints",
	"chat_inbox_views",
	"chat_inbox_view_checkpoints",
	"circle_group_membership_projection_states",
	"circle_group_chat_binding_projection_states",
	"circle_group_chat_sync_failures",
	"chat_user_account_closed_inbox",
	"chat_user_account_closed_failures",
	"chat_user_account_restrictions",
	"chat_user_account_restriction_inbox",
	"chat_user_account_restriction_watermarks",
	"message_receipts",
	"reliable_task_outbox",
	"reliable_async_task",
	"notification_outbox",
	"notification_delivery_ledger",
	"reliable_task_leases",
}

func requireMongoDB(tb testing.TB) *mongo.Database {
	tb.Helper()
	if mongoDB == nil {
		tb.Fatal("chat-service tests require TestMain to provision mongoDB or exit before execution")
	}
	return mongoDB
}

// testProfileResolver returns deterministic display names for contract tests.
type testProfileResolver struct{}

type testMediaAssetDeliveryReader struct{}

type staticAvatarRoundTripper struct {
	png []byte
}

func (transport staticAvatarRoundTripper) RoundTrip(request *http.Request) (*http.Response, error) {
	return &http.Response{
		StatusCode: http.StatusOK,
		Status:     "200 OK",
		Header:     http.Header{"Content-Type": []string{"image/png"}},
		Body:       io.NopCloser(bytes.NewReader(transport.png)),
		Request:    request,
	}, nil
}

func newGroupAvatarMediaForContractTest() *runtimemedia.GroupAvatarService {
	pngBytes, err := runtimemedia.RenderGroupAvatarImagesPNG(make([]image.Image, 1), 32)
	if err != nil {
		panic("render contract avatar source: " + err.Error())
	}
	return runtimemedia.NewGroupAvatarService(
		redisRouter.Scene("general"),
		"https://127.0.0.1:18081",
		testChatMediaRoot,
		runtimemedia.WithGroupAvatarHTTPClient(&http.Client{
			Transport: staticAvatarRoundTripper{png: pngBytes},
		}),
	)
}

func (testMediaAssetDeliveryReader) ReadOwnedReadyAsset(
	_ context.Context,
	assetID string,
	ownerPersonaID string,
) (messageports.MediaAssetDeliverySlice, bool, error) {
	mediaType := "file"
	switch {
	case strings.Contains(assetID, "audio"):
		mediaType = "audio"
	case strings.Contains(assetID, "image"):
		mediaType = "image"
	case strings.Contains(assetID, "video"):
		mediaType = "video"
	}
	return messageports.MediaAssetDeliverySlice{
		AssetID: assetID, OwnerPersonaID: ownerPersonaID,
		ProcessingStatus: "ready", MediaType: mediaType,
		ContentType: mediaType + "/test", FileSize: 2048,
		DeliveryURL: "https://media.test/" + assetID,
	}, true, nil
}

func (testProfileResolver) ResolveMany(ctx context.Context, userIDs []string) (map[string]application.ProfileSnapshot, error) {
	out := make(map[string]application.ProfileSnapshot, len(userIDs))
	for _, id := range userIDs {
		out[id] = application.ProfileSnapshot{
			UserHandle:    "handle_" + id,
			DisplayName:   "Display_" + id,
			AvatarURL:     fmt.Sprintf("media/avatar/s/archived-avatar/user/%s/v1/avatar.png", id),
			AvatarAssetID: "ua_" + id,
			AvatarVersion: 1,
			Bio:           "Bio_" + id,
		}
	}
	return out, nil
}

func TestMain(m *testing.M) {
	ctx, cancelRuntime := context.WithCancel(context.Background())

	var err error
	integrationRedis, err = testinfra.StartRealRedis(ctx)
	if err != nil {
		panic("chat-service api_integration requires real Redis: " + err.Error())
	}
	if err := integrationRedis.FlushDBs(ctx, 0, 1, 2, 3); err != nil {
		panic("flush chat-service integration Redis: " + err.Error())
	}

	redisRouter = platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general":      {Mode: "standalone", Addr: integrationRedis.Addr, Password: integrationRedis.Password, DB: 0, TLS: integrationRedis.TLS},
			"realtime":     {Mode: "standalone", Addr: integrationRedis.Addr, Password: integrationRedis.Password, DB: 1, TLS: integrationRedis.TLS},
			"reliabletask": {Mode: "standalone", Addr: integrationRedis.Addr, Password: integrationRedis.Password, DB: 2, TLS: integrationRedis.TLS},
			"rec":          {Mode: "standalone", Addr: integrationRedis.Addr, Password: integrationRedis.Password, DB: 3, TLS: integrationRedis.TLS},
		},
		PrefixRoutes: rtredis.DefaultRouterConfig().PrefixRoutes,
		DefaultScene: "general",
	})

	var mongoContainer *mongomod.MongoDBContainer

	mongoURI := os.Getenv("TEST_MONGO_URI")
	if mongoURI == "" {
		container, runErr := tryRunMongoContainer(ctx)
		if runErr != nil {
			panic(
				"chat-service api_integration requires a real MongoDB; " +
					"set TEST_MONGO_URI or start Docker: " + runErr.Error(),
			)
		}
		mongoContainer = container
		uri, connErr := container.ConnectionString(ctx)
		if connErr != nil {
			panic("failed to get mongo connection string: " + connErr.Error())
		}
		mongoURI = uri
	}

	mongoClientOptions := mongoopts.Client().ApplyURI(mongoURI)
	if mongoContainer != nil {
		// Colima forwards the replica-set member through localhost while Mongo
		// advertises its container IP. Direct mode keeps the client on the
		// reachable seed; rs0 still provides transaction semantics.
		mongoClientOptions.SetDirect(true)
	}
	mongoClient, err = mongo.Connect(mongoClientOptions)
	if err != nil {
		panic("failed to connect to mongo: " + err.Error())
	}
	mongoDB = mongoClient.Database("chat_test")
	chatStore := persistence.NewMongoChatStore(mongoDB)
	if err := chatStore.EnsureIndexes(ctx); err != nil {
		panic("failed to ensure chat aggregate indexes: " + err.Error())
	}
	membershipStore := membershippersistence.NewMongoStore(mongoDB)
	if err := membershipStore.EnsureIndexes(ctx); err != nil {
		panic("failed to ensure ConversationMembership indexes: " + err.Error())
	}
	if err := userstatepersistence.NewMongoStore(mongoDB).EnsureIndexes(ctx); err != nil {
		panic("failed to ensure ConversationUserState indexes: " + err.Error())
	}
	testInboxViewStore = inboxpersistence.NewMongoStore(mongoDB)
	if err := testInboxViewStore.EnsureIndexes(ctx); err != nil {
		panic("failed to ensure ChatInboxView indexes: " + err.Error())
	}
	if err := receiptpersistence.NewMongoStore(mongoDB).EnsureIndexes(ctx); err != nil {
		panic("failed to ensure MessageReceiptFact indexes: " + err.Error())
	}
	chatStorage := chatStoragePorts(chatStore)
	convCache := chatcache.NewConversationCache(redisRouter.Scene("general"))

	mediaDir, mediaErr := os.MkdirTemp("", "chat-group-media-*")
	if mediaErr != nil {
		panic("failed to create chat media temp dir: " + mediaErr.Error())
	}
	testChatMediaRoot = mediaDir

	eventPublisher := mq.NewEventPublisher(
		redisRouter.Scene("realtime"),
		redisRouter.Scene("general"),
		mq.NewMemberRecipientResolver(func(ctx context.Context, conversationID string) ([]string, error) {
			members, err := membershipStore.ListMembers(
				ctx,
				conversationID,
				application.ListMembersQuery{Limit: 512, Sort: application.MemberListSortJoinedAsc},
			)
			if err != nil {
				return nil, err
			}
			ids := make([]string, 0, len(members))
			for _, member := range members {
				ids = append(ids, member.UserId)
			}
			return ids, nil
		}),
	)
	testEventPublisher = eventPublisher
	testMessageOutboxRelay = application.NewMessageOutboxRelay(
		chatStore,
		chatStore,
		chatStore,
		eventPublisher,
		"chat-api-integration",
	)
	testProjectionCheckpoints := persistence.NewMongoProjectionCheckpointStore(mongoDB)
	testAggregateOutboxRelays = []*application.AggregateOutboxRelay{
		application.NewAggregateOutboxRelay(
			chatStorage.ConversationCommands.(*persistence.MongoAggregateCommandStore),
			testProjectionCheckpoints,
			eventPublisher,
			"chat-api-integration-conversation",
		),
		application.NewAggregateOutboxRelay(
			chatStorage.MembershipCommands.(*persistence.MongoAggregateCommandStore),
			testProjectionCheckpoints,
			eventPublisher,
			"chat-api-integration-membership",
		),
		application.NewAggregateOutboxRelay(
			chatStorage.UserStateCommands.(*persistence.MongoAggregateCommandStore),
			testProjectionCheckpoints,
			eventPublisher,
			"chat-api-integration-user-state",
		),
	}
	userStateStore := userstatepersistence.NewMongoStore(mongoDB)
	testInboxViewProjector = inboxapp.NewProjector(
		testInboxViewStore,
		testInboxViewStore,
		testInboxSnapshotSource{conversations: chatStore, states: userStateStore},
		testInboxMembershipReader{store: membershipStore},
		testInboxStateAdvancer{store: userStateStore},
		map[string]inboxapp.EventSource{
			"message": testInboxMessageSource{source: chatStore},
			"conversation": testInboxAggregateSource{
				source: chatStorage.ConversationCommands.(*persistence.MongoAggregateCommandStore),
			},
			"membership": testInboxAggregateSource{
				source: chatStorage.MembershipCommands.(*persistence.MongoAggregateCommandStore),
			},
			"user_state": testInboxAggregateSource{
				source: chatStorage.UserStateCommands.(*persistence.MongoAggregateCommandStore),
			},
		},
	)
	const testAvatarCDNBase = "https://127.0.0.1:18081"
	application.ConfigureGroupAvatarCDNBase(testAvatarCDNBase)
	if err := runtimemedia.EnsureDefaultGroupAvatarFile(testChatMediaRoot); err != nil {
		panic("failed to create default group avatar: " + err.Error())
	}
	groupAvatarMedia := newGroupAvatarMediaForContractTest()
	testGroupAvatarMedia = groupAvatarMedia
	userSyncService := runtimesync.NewService(redisRouter.Scene("general"), redisRouter.Scene("realtime"))
	testUserSyncPublisher = userSyncService
	catalog, err := reliabletask.LoadCatalog(testReliableTaskCatalogPath())
	if err != nil {
		panic("failed to load reliable task catalog: " + err.Error())
	}
	reliableTaskStore := reliabletaskmongo.New(mongoDB)
	if err := reliableTaskStore.EnsureIndexes(ctx); err != nil {
		panic("failed to ensure reliable task indexes: " + err.Error())
	}
	readyIndex, err := reliabletask.NewRedisReadyIndex(reliabletask.RedisReadyIndexConfig{
		Client: redisRouter.Scene("reliabletask"),
		Stream: "reliabletask:chat:avatar:ready:testmain",
		Group:  "chat.group_avatar_worker.testmain",
		Queue:  "reliabletask.chat.avatar",
	})
	if err != nil {
		panic("failed to init reliable task ready index: " + err.Error())
	}
	if err := readyIndex.Ensure(ctx); err != nil {
		panic("failed to ensure reliable task ready index: " + err.Error())
	}
	groupAvatarScheduler := application.NewReliableGroupAvatarTaskScheduler(
		reliableTaskStore,
		catalog,
		chatStorage,
		eventPublisher,
		groupAvatarMedia,
		userSyncService,
		slog.Default(),
		application.WithReliableGroupAvatarDelay(80*time.Millisecond),
		application.WithReliableGroupAvatarTick(40*time.Millisecond),
		application.WithReliableGroupAvatarReadyIndex(readyIndex),
	)
	testGroupAvatarScheduler = groupAvatarScheduler
	// 全包集成测试由等待 helper 显式 drain 这个共享 scheduler，避免它与验证
	// 失败/重试语义的用例内 scheduler 竞争同一可靠任务。生产装配仍由 root context Start。

	profiles := testProfileResolver{}
	relationshipContractServer, testRelationshipGate = startRelationshipContractRuntime(
		application.RelationshipCapability{
			CanCreateDirectConversation: true,
			CanSendMessage:              true,
			HasFormalConversation:       true,
			IsMutual:                    true,
		},
		map[string]application.RelationshipCapability{
			// 关系 gate 负例专用目标：非互关 / 已拉黑。
			"user_not_mutual_target": {
				CanCreateDirectConversation: false,
				CanSendMessage:              false,
				HasFormalConversation:       false,
				IsMutual:                    false,
			},
			"user_blocked_target": {
				IsBlocked: true,
			},
		},
	)
	conversationSvc := application.NewConversationService(
		chatStorage,
		convCache,
		eventPublisher,
		profiles,
		testRelationshipGate,
		groupAvatarMedia,
		userSyncService,
		groupAvatarScheduler,
	)
	messageSvc := application.NewMessageService(
		chatStorage,
		convCache,
		eventPublisher,
		testRelationshipGate,
		testMediaAssetDeliveryReader{},
	)
	testMessageService = messageSvc
	// 与生产 composition 对齐：公告命令经消息主线触达。
	conversationSvc.SetAnnouncementMessageSender(messageSvc)
	memberSvc := application.NewMemberService(
		chatStorage,
		convCache,
		eventPublisher,
		profiles,
		groupAvatarMedia,
		userSyncService,
		groupAvatarScheduler,
		application.WithRelationshipGate(testRelationshipGate),
	)
	inboxSvc := newTestInboxService()
	userAvatarConsumer := mq.NewUserAvatarUpdateConsumer(
		redisRouter.Scene("general"),
		chatStorage,
		eventPublisher,
		groupAvatarMedia,
		userSyncService,
		groupAvatarScheduler,
		slog.Default(),
	)
	if err := userAvatarConsumer.Start(ctx); err != nil {
		panic("failed to start user avatar consumer: " + err.Error())
	}

	chatHandler := chathttp.NewChatHandler(
		conversationSvc,
		messageSvc,
		memberSvc,
		inboxSvc,
		userSyncService,
	)
	chatRoutes := http.NewServeMux()
	inboxhttp.NewHandler(testInboxViewStore).Register(chatRoutes)
	membershiphttp.NewHandler(memberSvc).Register(chatRoutes)
	userstatehttp.NewHandler(messageSvc, conversationSvc).Register(chatRoutes)
	messagehttp.NewHandler(messageSvc).Register(chatRoutes)
	chatRoutes.HandleFunc(
		"GET /chat/conversations/{conversationId}/messages/{messageId}/receipts",
		receipthttp.NewHandler(messageSvc).GetReceipts,
	)
	chatHandler.RegisterRoutes(chatRoutes)
	chatRoutes.Handle("/media/", testDerivedMediaFileServer(testChatMediaRoot))
	testHandler = chatRoutes

	code := m.Run()

	cancelRuntime()
	// 两个后台消费者都由上面的 context 驱动；给 goroutine 一个 tick 内退出，
	// 再关闭真实 Mongo/Redis，避免 teardown 将正常取消误报为依赖故障。
	time.Sleep(100 * time.Millisecond)
	relationshipContractServer.Close()
	_ = mongoClient.Disconnect(ctx)
	if mongoContainer != nil {
		_ = mongoContainer.Terminate(ctx)
	}
	_ = redisRouter.Close()
	_ = integrationRedis.Close(ctx)
	os.Exit(code)
}

func testReliableTaskCatalogPath() string {
	_, sourceFile, _, ok := runtime.Caller(0)
	if !ok {
		panic("resolve chat-service api integration source location")
	}
	return filepath.Clean(filepath.Join(
		filepath.Dir(sourceFile),
		"../../../../../../../quwoquan_service/runtime/reliabletask/resources/module_catalog.yaml",
	))
}

func tryRunMongoContainer(ctx context.Context) (c *mongomod.MongoDBContainer, err error) {
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("testcontainers panic (Docker unavailable?): %v", r)
		}
	}()
	c, err = mongomod.Run(ctx, "mongo:7-jammy", mongomod.WithReplicaSet("rs0"))
	return
}

func cleanAll(t *testing.T) {
	t.Helper()
	if mongoDB == nil {
		return
	}
	ctx := context.Background()
	for _, name := range collections {
		_, _ = mongoDB.Collection(name).DeleteMany(ctx, bson.M{})
	}
	if err := integrationRedis.FlushDBs(ctx, 0, 1, 2, 3); err != nil {
		t.Fatalf("flush chat integration Redis: %v", err)
	}
}
