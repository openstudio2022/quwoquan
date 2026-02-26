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

	rtrec "quwoquan_service/runtime/recommendation"
	"quwoquan_service/runtime/testinfra"
	contenhttp "quwoquan_service/services/content-service/internal/adapters/http"
	"quwoquan_service/services/content-service/internal/application"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
	recinfra "quwoquan_service/services/content-service/internal/infrastructure/recommendation"
)

var (
	testHandler http.Handler
	eventSpy    *testinfra.EventSpy
	mongoDB     *mongo.Database
	mongoClient *mongo.Client
)

func TestMain(m *testing.M) {
	ctx := context.Background()

	eventSpy = testinfra.NewEventSpy()

	// Start miniredis (no *testing.T required).
	mr, err := miniredis.Run()
	if err != nil {
		panic("failed to start miniredis: " + err.Error())
	}

	// Start MongoDB testcontainer (mongo:7-jammy) for realistic L2 tests.
	// Falls back to TEST_MONGO_URI env var for CI environments that pre-provision Mongo.
	// When Docker is unavailable locally, prints a warning and skips all L2 tests.
	var postStore persistence.PostRepository
	var mongoContainer *mongomod.MongoDBContainer

	mongoURI := os.Getenv("TEST_MONGO_URI")
	if mongoURI == "" {
		container, runErr := tryRunMongoContainer(ctx)
		if runErr != nil {
			// Docker not available locally: skip rather than panic.
			// In CI (GITHUB_ACTIONS=true or CI=true), fail to force gate failure.
			if os.Getenv("CI") == "true" || os.Getenv("GITHUB_ACTIONS") == "true" {
				panic("CI: failed to start mongo testcontainer: " + runErr.Error())
			}
			fmt.Fprintf(os.Stderr,
				"\n[L2] WARN: Docker unavailable, skipping content-service L2 tests.\n"+
					"  Set TEST_MONGO_URI=mongodb://localhost:27017 to run without Docker.\n"+
					"  Error: %v\n\n", runErr)
			os.Exit(0) // local skip: exit 0 = tests "skipped"
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
	mongoDB = mongoClient.Database("content_test")
	postStore = persistence.NewMongoPostStore(mongoDB.Collection("posts"))

	// Wire services with the real MongoDB store.
	redis := recinfra.NewRedisClientAdapter(mr.Addr(), "", 0)
	hotPath := rtrec.NewHotPath(redis)
	source := recinfra.NewPostRepositorySource(postStore)
	engine := rtrec.NewEngine(hotPath, []rtrec.CandidateSource{source})
	feedService := application.NewFeedService(engine, source)
	postService := application.NewPostService(
		postStore,
		application.WithEventPublisher(eventSpy),
	)
	behaviorService := application.NewBehaviorService(hotPath, postStore)
	testHandler = contenhttp.NewContentHandler(feedService, postService, behaviorService).Routes()

	code := m.Run()

	// Teardown: disconnect and terminate in reverse order.
	_ = mongoClient.Disconnect(ctx)
	if mongoContainer != nil {
		_ = mongoContainer.Terminate(ctx)
	}
	mr.Close()
	os.Exit(code)
}

// tryRunMongoContainer attempts to start a mongo:7-jammy testcontainer.
// Returns (nil, err) when Docker is unavailable or the container fails to start,
// capturing both returned errors and internal panics from the testcontainers runtime.
func tryRunMongoContainer(ctx context.Context) (c *mongomod.MongoDBContainer, err error) {
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("testcontainers panic (Docker unavailable?): %v", r)
		}
	}()
	c, err = mongomod.Run(ctx, "mongo:7-jammy")
	return
}

// cleanPosts deletes all documents from the posts collection to isolate tests.
func cleanPosts(t *testing.T) {
	t.Helper()
	if mongoDB == nil {
		return
	}
	_, err := mongoDB.Collection("posts").DeleteMany(context.Background(), bson.M{})
	if err != nil {
		t.Logf("cleanPosts: %v", err)
	}
	eventSpy.Reset()
}
