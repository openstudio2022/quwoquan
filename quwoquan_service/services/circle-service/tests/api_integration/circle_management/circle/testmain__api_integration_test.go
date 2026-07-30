package api_integration

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"strconv"
	"strings"
	"testing"

	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	httpadapter "quwoquan_service/services/circle-service/internal/circle_management/circle/adapters/inbound/http"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
	circleports "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/ports"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/cache"
	circlepersistence "quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/circle/persistence"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/messaging"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/persistence"
	behaviorfactapp "quwoquan_service/services/circle-service/internal/circle_management/circle_behavior_fact/application"
	behaviorfactpersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_behavior_fact/infrastructure/persistence"
	fileapp "quwoquan_service/services/circle-service/internal/circle_management/circle_file/application"
	fileports "quwoquan_service/services/circle-service/internal/circle_management/circle_file/domain/ports"
	filepersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_file/infrastructure/persistence"
	groupapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group/application"
	grouppersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_group/infrastructure/persistence"
	groupmembershipapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/application"
	groupmembershippersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/infrastructure/persistence"
	membershipapp "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/application"
	membershippersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/infrastructure/persistence"
	placementapp "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/application"
	placementports "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/domain/ports"
	placementpersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/infrastructure/persistence"
)

var (
	testHandler            http.Handler
	eventSpy               *testinfra.EventSpy
	mongoDB                *mongo.Database
	mongoClient            *mongo.Client
	integrationRedis       *testinfra.RealRedis
	redisRouter            *rtredis.Router
	circleMessageTransport *runtimemessaging.RedisMessageTransport
	fileStreamRelay        *fileapp.OutboxRelay
	circleEventRelay       *application.CircleOutboxRelay
	circleCacheInvalidator circleports.CacheInvalidator
)

// placementRoleReaderAdapter 复用 placement policy readers 的成员角色读，
// 适配 Circle 本体命令权限端口。
type placementRoleReaderAdapter struct {
	readers *placementpersistence.MongoPolicyReaders
}

func (adapter placementRoleReaderAdapter) ReadMembershipRole(ctx context.Context, circleID, personaID string) (string, string, bool, error) {
	slice, found, err := adapter.readers.ReadMembershipRole(ctx, circleID, personaID)
	if err != nil || !found {
		return "", "", found, err
	}
	return slice.Role, slice.State, true, nil
}

type readyMediaAssetReader struct{}

// ReadOwnedReadyAsset 返回权威 MediaAsset 视图；`asset-bytes-<n>` 形式的
// asset id 把 n 作为权威尺寸，供配额约束测试驱动。
func (readyMediaAssetReader) ReadOwnedReadyAsset(
	_ context.Context,
	assetID string,
	ownerPersonaID string,
) (fileports.MediaAssetOwnerSlice, bool, error) {
	if assetID == "" || ownerPersonaID == "" {
		return fileports.MediaAssetOwnerSlice{}, false, nil
	}
	fileSize := int64(1024)
	if rest, ok := strings.CutPrefix(assetID, "asset-bytes-"); ok {
		if parsed, err := strconv.ParseInt(rest, 10, 64); err == nil {
			fileSize = parsed
		}
	}
	return fileports.MediaAssetOwnerSlice{
		AssetID: assetID, OwnerPersonaID: ownerPersonaID, ProcessingStatus: "ready",
		ContentType: "application/pdf", FileSize: fileSize,
	}, true, nil
}

func TestMain(m *testing.M) {
	ctx := context.Background()

	eventSpy = testinfra.NewEventSpy()

	var err error
	integrationRedis, err = testinfra.StartRealRedis(ctx)
	if err != nil {
		panic("circle-service api_integration requires real Redis: " + err.Error())
	}
	if err := integrationRedis.FlushDBs(ctx, 0); err != nil {
		panic("flush circle-service integration Redis: " + err.Error())
	}
	redisRouter = platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {Mode: "standalone", Addr: integrationRedis.Addr, Password: integrationRedis.Password, DB: 0, TLS: integrationRedis.TLS},
		},
		DefaultScene: "general",
	})

	var mongoContainer *mongomod.MongoDBContainer
	mongoURI := os.Getenv("TEST_MONGO_URI")
	if mongoURI == "" {
		container, runErr := tryRunMongoContainer(ctx)
		if runErr != nil {
			panic(
				"circle-service api_integration requires a real MongoDB; " +
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
		mongoClientOptions.SetDirect(true)
	}
	mongoClient, err = mongo.Connect(mongoClientOptions)
	if err != nil {
		panic("failed to connect to mongo: " + err.Error())
	}
	mongoDB = mongoClient.Database("circle_test")

	circleStore := persistence.NewMongoCircleStore(mongoDB.Collection("circles"))
	fileStore := filepersistence.NewMongoAggregateStore(mongoDB)
	if err := fileStore.EnsureIndexes(ctx); err != nil {
		panic("ensure CircleFile indexes: " + err.Error())
	}
	fileReaders := filepersistence.NewMongoReaders(mongoDB)
	groupStore := grouppersistence.NewMongoAggregateStore(mongoDB)
	if err := groupStore.EnsureIndexes(ctx); err != nil {
		panic("ensure CircleGroup indexes: " + err.Error())
	}
	groupReaders := grouppersistence.NewMongoReaders(mongoDB)
	groupMembershipStore := groupmembershippersistence.NewMongoAggregateStore(mongoDB)
	if err := groupMembershipStore.EnsureIndexes(ctx); err != nil {
		panic("ensure CircleGroupMembership indexes: " + err.Error())
	}
	groupMembershipReaders := groupmembershippersistence.NewMongoReaders(mongoDB)

	// Cache contract crosses a real Redis network boundary.
	rdb := redisRouter.Scene("general")
	circleMessageTransport, err = runtimemessaging.NewRedisMessageTransportForRoot(
		"circle-service-api",
		runtimemessaging.RedisMessageTransportAdapter,
		rdb,
		rdb,
	)
	if err != nil {
		panic("create circle integration message transport: " + err.Error())
	}
	cachedCircleStore := cache.NewCachedCircleStore(circleStore, rdb)
	circleCacheInvalidator = cachedCircleStore
	circleStorage := application.CircleStoragePorts{Records: cachedCircleStore}
	circleAggregateStore := circlepersistence.NewMongoAggregateStore(mongoDB)
	if err := circleAggregateStore.EnsureIndexes(ctx); err != nil {
		panic("ensure Circle aggregate indexes: " + err.Error())
	}

	feedStore := persistence.NewMongoFeedStore(mongoDB)
	discoveryFeedReader := persistence.NewMongoCircleDiscoveryFeedReader(mongoDB)
	if err := discoveryFeedReader.EnsureIndexes(ctx); err != nil {
		panic("ensure circle discovery feed indexes: " + err.Error())
	}
	cachedDiscoveryFeedReader := cache.NewCachedCircleDiscoveryFeedReader(
		discoveryFeedReader,
		rdb,
	)
	placementStore := placementpersistence.NewMongoAggregateStore(mongoDB)
	if err := placementStore.EnsureIndexes(ctx); err != nil {
		panic("ensure placement indexes: " + err.Error())
	}
	placementReaders := placementpersistence.NewMongoPolicyReaders(mongoDB)
	if err := placementReaders.EnsureIndexes(ctx); err != nil {
		panic("ensure placement reader indexes: " + err.Error())
	}
	membershipStore := membershippersistence.NewMongoAggregateStore(mongoDB)
	if err := membershipStore.EnsureIndexes(ctx); err != nil {
		panic("ensure membership indexes: " + err.Error())
	}
	membershipReaders := membershippersistence.NewMongoReaders(mongoDB)
	behaviorFactStore := behaviorfactpersistence.NewMongoAppendSink(mongoDB)
	if err := behaviorFactStore.EnsureIndexes(ctx); err != nil {
		panic("ensure behavior fact indexes: " + err.Error())
	}

	circleService := application.NewCircleService(
		circleStorage,
		application.WithFeedStore(feedStore),
		application.WithDiscoveryFeedReader(cachedDiscoveryFeedReader),
	)
	circleCommands := application.NewCircleCommandFacade(
		circleAggregateStore,
		placementRoleReaderAdapter{readers: placementReaders},
		cachedCircleStore,
		nil,
	)
	circleEventRelay = application.NewCircleOutboxRelay(
		circleAggregateStore, circleAggregateStore,
		application.NewCircleDomainEventSink(eventSpy),
		"circle-event-spy",
	)
	fileCommands := fileapp.NewCommandFacade(fileStore, fileReaders, readyMediaAssetReader{})
	fileQueries := fileapp.NewQueryFacade(fileReaders, fileReaders)
	fileStreamRelay = fileapp.NewOutboxRelay(
		fileStore, fileStore, messaging.NewCircleFileStreamPublisher(circleMessageTransport), "circle-file-stream",
	)
	placementCommands := placementapp.NewCommandFacade(placementStore, placementports.PolicyReaders{
		Circles: placementReaders, Groups: placementReaders,
		Posts: placementReaders, Memberships: placementReaders,
	})
	membershipCommands := membershipapp.NewCommandFacade(membershipStore, membershipReaders, membershipReaders)
	membershipQueries := membershipapp.NewQueryFacade(membershipReaders, membershipReaders, membershipReaders)
	behaviorFactWriter := behaviorfactapp.NewWriter(behaviorFactStore, behaviorFactStore)
	groupCommands := groupapp.NewCommandFacade(groupStore, groupReaders)
	groupQueries := groupapp.NewQueryFacade(groupReaders, groupReaders)
	groupMembershipCommands := groupmembershipapp.NewCommandFacade(
		groupMembershipStore, groupMembershipReaders, groupMembershipReaders, groupMembershipReaders,
	)
	groupMembershipQueries := groupmembershipapp.NewQueryFacade(groupMembershipReaders, groupMembershipReaders)

	testHandler = httpadapter.NewCircleHandler(
		circleService, circleCommands, fileCommands, fileQueries, behaviorFactWriter, groupCommands, groupQueries,
		groupMembershipCommands, groupMembershipQueries,
		membershipCommands, membershipQueries, placementCommands,
	).Routes()

	code := m.Run()

	_ = mongoClient.Disconnect(ctx)
	if mongoContainer != nil {
		_ = mongoContainer.Terminate(ctx)
	}
	_ = redisRouter.Close()
	_ = integrationRedis.Close(ctx)
	os.Exit(code)
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

func cleanCollections(t *testing.T) {
	t.Helper()
	if mongoDB == nil {
		return
	}
	for _, coll := range []string{
		"circles", "circle_memberships", "circle_files", "circle_groups", "posts",
		"circle_membership_command_receipts", "circle_membership_outbox",
		"circle_membership_outbox_sequences", "circle_membership_projection_checkpoints",
		"circle_membership_projection_inbox",
		"circle_group_memberships", "circle_group_command_receipts", "circle_group_outbox",
		"circle_group_outbox_sequences", "circle_group_projection_checkpoints",
		"circle_group_membership_capacity_counters", "circle_group_membership_command_receipts", "circle_group_membership_outbox",
		"circle_group_membership_outbox_sequences", "circle_group_membership_projection_checkpoints",
		"circle_behavior_facts", "circle_behavior_fact_outbox",
		"circle_behavior_fact_outbox_sequences", "circle_behavior_fact_projection_checkpoints",
		"circle_behavior_fact_projection_inbox",
		"circle_post_owner_views", "circle_post_placements",
		"circle_post_placement_command_receipts", "circle_post_placement_outbox",
		"circle_post_placement_outbox_sequences", "circle_post_placement_projection_checkpoints",
		"circle_post_placement_projection_inbox", "circle_content_post_inbox",
		"circle_content_post_failures",
		"circle_files_command_receipts", "circle_files_outbox", "circle_files_outbox_sequences",
		"circle_files_projection_checkpoints", "circle_files_quota_locks",
		"circle_command_receipts", "circle_outbox", "circle_outbox_sequences",
		"circle_projection_checkpoints",
		"circle_user_account_closed_inbox", "circle_user_account_closed_failures",
		"circle_closed_account_subjects",
		"circle_user_account_restrictions", "circle_user_account_restriction_inbox",
		"circle_user_account_restriction_watermarks",
	} {
		mongoDB.Collection(coll).DeleteMany(context.Background(), bson.M{})
	}
	if err := integrationRedis.FlushDBs(context.Background(), 0); err != nil {
		t.Fatalf("flush circle integration Redis: %v", err)
	}
	eventSpy.Reset()
}
