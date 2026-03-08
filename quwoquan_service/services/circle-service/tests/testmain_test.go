package tests

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"testing"

	"github.com/alicebob/miniredis/v2"
	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/testinfra"
	httpadapter "quwoquan_service/services/circle-service/internal/adapters/http"
	"quwoquan_service/services/circle-service/internal/application"
	"quwoquan_service/services/circle-service/internal/infrastructure/cache"
	"quwoquan_service/services/circle-service/internal/infrastructure/persistence"
)

var (
	testHandler http.Handler
	eventSpy    *testinfra.EventSpy
	mongoDB     *mongo.Database
	mongoClient *mongo.Client
	mr          *miniredis.Miniredis
)

func TestMain(m *testing.M) {
	ctx := context.Background()

	eventSpy = testinfra.NewEventSpy()

	var err error
	mr, err = miniredis.Run()
	if err != nil {
		panic("failed to start miniredis: " + err.Error())
	}

	var mongoContainer *mongomod.MongoDBContainer
	mongoURI := os.Getenv("TEST_MONGO_URI")
	if mongoURI == "" {
		container, runErr := tryRunMongoContainer(ctx)
		if runErr != nil {
			if os.Getenv("CI") == "true" || os.Getenv("GITHUB_ACTIONS") == "true" {
				panic("CI: failed to start mongo testcontainer: " + runErr.Error())
			}
			fmt.Fprintf(os.Stderr,
				"\n[L2] WARN: Docker unavailable, skipping circle-service L2 tests.\n"+
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
	mongoDB = mongoClient.Database("circle_test")

	circleStore := persistence.NewMongoCircleStore(mongoDB.Collection("circles"))
	memberStore := persistence.NewMongoMemberStore(mongoDB.Collection("circle_members"))
	fileStore := persistence.NewMongoFileStore(mongoDB.Collection("circle_files"))

	// Wrap with Redis cache
	rdb := cache.NewMiniredisClient(mr.Addr())
	cachedCircleStore := cache.NewCachedCircleStore(circleStore, rdb)

	feedStore := persistence.NewMongoFeedStore(mongoDB.Collection("posts"))

	circleService := application.NewCircleService(
		cachedCircleStore, memberStore, fileStore,
		application.WithEventPublisher(eventSpy),
		application.WithFeedStore(feedStore),
	)
	fileService := application.NewFileService(fileStore, cachedCircleStore)

	testHandler = httpadapter.NewCircleHandler(circleService, fileService).Routes()

	code := m.Run()

	_ = mongoClient.Disconnect(ctx)
	if mongoContainer != nil {
		_ = mongoContainer.Terminate(ctx)
	}
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

func cleanCollections(t *testing.T) {
	t.Helper()
	if mongoDB == nil {
		return
	}
	for _, coll := range []string{"circles", "circle_members", "circle_files", "posts"} {
		mongoDB.Collection(coll).DeleteMany(context.Background(), bson.M{})
	}
	mr.FlushAll()
	eventSpy.Reset()
}
