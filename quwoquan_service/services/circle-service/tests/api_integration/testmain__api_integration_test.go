package api_integration

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"testing"

	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtredis "quwoquan_service/runtime/redis"
	httpadapter "quwoquan_service/services/circle-service/internal/adapters/http"
	"quwoquan_service/services/circle-service/internal/application"
	behaviorfactapp "quwoquan_service/services/circle-service/internal/application/circle/circle_behavior_fact"
	fileapp "quwoquan_service/services/circle-service/internal/application/circle/circle_file"
	groupapp "quwoquan_service/services/circle-service/internal/application/circle/circle_group"
	groupmembershipapp "quwoquan_service/services/circle-service/internal/application/circle/circle_group_membership"
	membershipapp "quwoquan_service/services/circle-service/internal/application/circle/circle_membership"
	placementapp "quwoquan_service/services/circle-service/internal/application/circle/circle_post_placement"
	fileports "quwoquan_service/services/circle-service/internal/domain/circle/circle_file/ports"
	placementports "quwoquan_service/services/circle-service/internal/domain/circle/circle_post_placement/ports"
	"quwoquan_service/services/circle-service/internal/infrastructure/cache"
	behaviorfactpersistence "quwoquan_service/services/circle-service/internal/infrastructure/circle/circle_behavior_fact/persistence"
	filepersistence "quwoquan_service/services/circle-service/internal/infrastructure/circle/circle_file/persistence"
	grouppersistence "quwoquan_service/services/circle-service/internal/infrastructure/circle/circle_group/persistence"
	groupmembershippersistence "quwoquan_service/services/circle-service/internal/infrastructure/circle/circle_group_membership/persistence"
	membershippersistence "quwoquan_service/services/circle-service/internal/infrastructure/circle/circle_membership/persistence"
	placementpersistence "quwoquan_service/services/circle-service/internal/infrastructure/circle/circle_post_placement/persistence"
	"quwoquan_service/services/circle-service/internal/infrastructure/messaging"
	"quwoquan_service/services/circle-service/internal/infrastructure/persistence"
)

var (
	testHandler      http.Handler
	eventSpy         *testinfra.EventSpy
	mongoDB          *mongo.Database
	mongoClient      *mongo.Client
	integrationRedis *testinfra.RealRedis
	redisRouter      *rtredis.Router
	fileStreamRelay  *fileapp.OutboxRelay
)

type readyMediaAssetReader struct{}

func (readyMediaAssetReader) ReadOwnedReadyAsset(
	_ context.Context,
	assetID string,
	ownerPersonaID string,
) (fileports.MediaAssetOwnerSlice, bool, error) {
	if assetID == "" || ownerPersonaID == "" {
		return fileports.MediaAssetOwnerSlice{}, false, nil
	}
	return fileports.MediaAssetOwnerSlice{
		AssetID: assetID, OwnerPersonaID: ownerPersonaID, ProcessingStatus: "ready",
		ContentType: "application/pdf", FileSize: 1024,
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
	cachedCircleStore := cache.NewCachedCircleStore(circleStore, circleStore, circleStore, rdb)
	circleStorage := application.CircleStoragePorts{
		Records: cachedCircleStore, Metrics: cachedCircleStore, Sections: cachedCircleStore,
		IDs: persistence.ObjectIDGenerator{},
	}

	feedStore := persistence.NewMongoFeedStore(mongoDB.Collection("posts"))
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
		application.WithEventPublisher(eventSpy),
		application.WithFeedStore(feedStore),
	)
	fileCommands := fileapp.NewCommandFacade(fileStore, fileReaders, readyMediaAssetReader{})
	fileQueries := fileapp.NewQueryFacade(fileReaders, fileReaders)
	fileStreamRelay = fileapp.NewOutboxRelay(
		fileStore, fileStore, messaging.NewCircleFileStreamPublisher(rdb), "circle-file-stream",
	)
	placementCommands := placementapp.NewCommandFacade(placementStore, placementports.PolicyReaders{
		Circles: placementReaders, Groups: placementReaders,
		Posts: placementReaders, Memberships: placementReaders,
	})
	membershipCommands := membershipapp.NewCommandFacade(membershipStore, membershipReaders, membershipReaders)
	membershipQueries := membershipapp.NewQueryFacade(membershipReaders, membershipReaders)
	behaviorFactWriter := behaviorfactapp.NewWriter(behaviorFactStore, behaviorFactStore)
	groupCommands := groupapp.NewCommandFacade(groupStore, groupReaders)
	groupQueries := groupapp.NewQueryFacade(groupReaders, groupReaders)
	groupMembershipCommands := groupmembershipapp.NewCommandFacade(
		groupMembershipStore, groupMembershipReaders, groupMembershipReaders, groupMembershipReaders,
	)
	groupMembershipQueries := groupmembershipapp.NewQueryFacade(groupMembershipReaders, groupMembershipReaders)

	testHandler = httpadapter.NewCircleHandler(
		circleService, fileCommands, fileQueries, behaviorFactWriter, groupCommands, groupQueries,
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
		"circle_group_membership_command_receipts", "circle_group_membership_outbox",
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
	} {
		mongoDB.Collection(coll).DeleteMany(context.Background(), bson.M{})
	}
	if err := integrationRedis.FlushDBs(context.Background(), 0); err != nil {
		t.Fatalf("flush circle integration Redis: %v", err)
	}
	eventSpy.Reset()
}
