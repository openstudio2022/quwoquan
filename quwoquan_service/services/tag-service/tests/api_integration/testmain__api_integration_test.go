package api_integration

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"testing"

	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

	httpadapter "quwoquan_service/services/tag-service/internal/adapters/http"
	"quwoquan_service/services/tag-service/internal/application"
	"quwoquan_service/services/tag-service/internal/infrastructure/persistence"
)

var (
	testHandler  http.Handler
	mongoDB      *mongo.Database
	mongoClient  *mongo.Client
	tagNodeStore *persistence.MongoTagNodeStore
	objStore     *persistence.MongoObjectTagIndexStore
)

func TestMain(m *testing.M) {
	ctx := context.Background()

	var mongoContainer *mongomod.MongoDBContainer
	mongoURI := os.Getenv("TEST_MONGO_URI")
	if mongoURI == "" {
		container, runErr := tryRunMongoContainer(ctx)
		if runErr != nil {
			if os.Getenv("CI") == "true" || os.Getenv("GITHUB_ACTIONS") == "true" {
				panic("CI: failed to start mongo testcontainer: " + runErr.Error())
			}
			fmt.Fprintf(os.Stderr,
				"\n[L2] WARN: Docker unavailable, skipping tag-service L2 tests.\n"+
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
	mongoURI = normalizeMongoURI(mongoURI)

	var err error
	mongoClient, err = mongo.Connect(mongoopts.Client().ApplyURI(mongoURI))
	if err != nil {
		panic("failed to connect to mongo: " + err.Error())
	}
	mongoDB = mongoClient.Database("tag_test")

	tagNodeStore = persistence.NewMongoTagNodeStore(mongoDB.Collection("tag_nodes"))
	objStore = persistence.NewMongoObjectTagIndexStore(mongoDB.Collection("object_tag_index"))
	_ = tagNodeStore.EnsureIndexes(ctx)
	_ = objStore.EnsureIndexes(ctx)

	svc := application.NewTagService(tagNodeStore, objStore)
	testHandler = httpadapter.NewTagHandler(svc).Routes()

	code := m.Run()

	_ = mongoClient.Disconnect(ctx)
	if mongoContainer != nil {
		_ = mongoContainer.Terminate(ctx)
	}
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
	for _, coll := range []string{"tag_nodes", "object_tag_index"} {
		mongoDB.Collection(coll).DeleteMany(context.Background(), bson.M{})
	}
}

// normalizeMongoURI 让本地 / 容器测试 URI 走直连，避免 server selection 长时间挂起。
func normalizeMongoURI(raw string) string {
	parsed, err := url.Parse(raw)
	if err != nil {
		return raw
	}
	if parsed.Path == "" {
		parsed.Path = "/"
	}
	query := parsed.Query()
	query.Set("directConnection", "true")
	query.Set("serverSelectionTimeoutMS", "5000")
	query.Set("connectTimeoutMS", "5000")
	parsed.RawQuery = query.Encode()
	return parsed.String()
}
