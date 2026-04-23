package tests

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"testing"

	"github.com/alicebob/miniredis/v2"
	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

	runtimemedia "quwoquan_service/runtime/media"
	rtredis "quwoquan_service/runtime/redis"
	runtimesync "quwoquan_service/runtime/sync"
	chathttp "quwoquan_service/services/chat-service/internal/adapters/http"
	"quwoquan_service/services/chat-service/internal/adapters/mq"
	"quwoquan_service/services/chat-service/internal/application"
	chatcache "quwoquan_service/services/chat-service/internal/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

var (
	testHandler http.Handler
	mongoDB     *mongo.Database
	mongoClient *mongo.Client
	mr          *miniredis.Miniredis
	redisRouter *rtredis.Router
)

var collections = []string{
	"conversations",
	"messages",
	"conversation_members",
	"conversation_user_states",
	"message_receipts",
}

// testProfileResolver returns deterministic display names for contract tests.
type testProfileResolver struct{}

func (testProfileResolver) ResolveMany(ctx context.Context, userIDs []string) (map[string]application.ProfileSnapshot, error) {
	out := make(map[string]application.ProfileSnapshot, len(userIDs))
	for _, id := range userIDs {
		out[id] = application.ProfileSnapshot{
			DisplayName:   "Display_" + id,
			AvatarURL:     "https://test.avatar/" + id,
			AvatarAssetID: "ua_" + id,
			AvatarVersion: 1,
		}
	}
	return out, nil
}

func TestMain(m *testing.M) {
	ctx := context.Background()

	var err error
	mr, err = miniredis.Run()
	if err != nil {
		panic("failed to start miniredis: " + err.Error())
	}

	redisRouter = rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general":  {Mode: "standalone", Addr: mr.Addr()},
			"realtime": {Mode: "standalone", Addr: mr.Addr()},
			"rec":      {Mode: "memory"},
		},
		PrefixRoutes: rtredis.DefaultRouterConfig().PrefixRoutes,
		DefaultScene: "general",
	})

	var mongoContainer *mongomod.MongoDBContainer

	mongoURI := os.Getenv("TEST_MONGO_URI")
	if mongoURI == "" {
		container, runErr := tryRunMongoContainer(ctx)
		if runErr != nil {
			if os.Getenv("CI") == "true" || os.Getenv("GITHUB_ACTIONS") == "true" {
				panic("CI: failed to start mongo testcontainer: " + runErr.Error())
			}
			fmt.Fprintf(os.Stderr,
				"\n[L2] WARN: Docker unavailable, skipping chat-service L2 tests.\n"+
					"  Set TEST_MONGO_URI=mongodb://localhost:27017 to run without Docker.\n"+
					"  Error: %v\n\n", runErr)
			os.Exit(0)
		}
		mongoContainer = container
		uri, connErr := container.ConnectionString(ctx)
		if connErr != nil {
			panic("failed to get mongo connection string: " + connErr.Error())
		}
		mongoURI = uri
	}

	mongoClient, err = mongo.Connect(mongoopts.Client().ApplyURI(mongoURI))
	if err != nil {
		panic("failed to connect to mongo: " + err.Error())
	}
	mongoDB = mongoClient.Database("chat_test")

	chatStore := persistence.NewMongoChatStore(mongoDB)
	convCache := chatcache.NewConversationCache(redisRouter.Scene("general"))

	eventPublisher := mq.NewEventPublisher(redisRouter.Scene("realtime"))
	groupAvatarMedia := runtimemedia.NewGroupAvatarService(redisRouter.Scene("general"), "")
	userSyncService := runtimesync.NewService(redisRouter.Scene("general"), redisRouter.Scene("realtime"))
	groupAvatarScheduler := application.NewRedisGroupAvatarTaskScheduler(
		redisRouter.Scene("general"),
		chatStore,
		eventPublisher,
		groupAvatarMedia,
		userSyncService,
		slog.Default(),
	)
	if err := groupAvatarScheduler.Start(ctx); err != nil {
		panic("failed to start group avatar scheduler: " + err.Error())
	}

	profiles := testProfileResolver{}
	conversationSvc := application.NewConversationService(
		chatStore,
		convCache,
		eventPublisher,
		profiles,
		groupAvatarMedia,
		userSyncService,
		groupAvatarScheduler,
	)
	messageSvc := application.NewMessageService(chatStore, convCache, eventPublisher)
	memberSvc := application.NewMemberService(
		chatStore,
		convCache,
		eventPublisher,
		profiles,
		groupAvatarMedia,
		userSyncService,
		groupAvatarScheduler,
	)
	inboxSvc := application.NewInboxService(chatStore)
	userAvatarConsumer := mq.NewUserAvatarUpdateConsumer(
		redisRouter.Scene("general"),
		chatStore,
		eventPublisher,
		groupAvatarMedia,
		userSyncService,
		groupAvatarScheduler,
		slog.Default(),
	)
	if err := userAvatarConsumer.Start(ctx); err != nil {
		panic("failed to start user avatar consumer: " + err.Error())
	}

	testHandler = chathttp.NewChatHandler(conversationSvc, messageSvc, memberSvc, inboxSvc).Routes()

	code := m.Run()

	_ = mongoClient.Disconnect(ctx)
	if mongoContainer != nil {
		_ = mongoContainer.Terminate(ctx)
	}
	_ = redisRouter.Close()
	mr.Close()
	os.Exit(code)
}

func tryRunMongoContainer(ctx context.Context) (c *mongomod.MongoDBContainer, err error) {
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("testcontainers panic (Docker unavailable?): %v", r)
		}
	}()
	c, err = mongomod.Run(ctx, "mongo:7-jammy")
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
	mr.FlushAll()
}
