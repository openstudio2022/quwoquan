package api_integration

import (
	"context"
	"fmt"
	"os"
	"testing"

	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"
)

var filterCatalogMongoDB *mongo.Database

func TestMain(m *testing.M) {
	ctx := context.Background()
	mongoURI := os.Getenv("TEST_MONGO_URI")
	var mongoContainer *mongomod.MongoDBContainer
	if mongoURI == "" {
		container, err := tryRunFilterCatalogMongoContainer(ctx)
		if err != nil {
			panic(
				"FilterCatalogRelease api_integration requires a real MongoDB; " +
					"set TEST_MONGO_URI or start Docker: " + err.Error(),
			)
		}
		mongoContainer = container
		uri, err := container.ConnectionString(ctx)
		if err != nil {
			panic("get FilterCatalogRelease MongoDB connection string: " + err.Error())
		}
		mongoURI = uri
	}

	options := mongoopts.Client().ApplyURI(mongoURI)
	if mongoContainer != nil {
		options.SetDirect(true)
	}
	client, err := mongo.Connect(options)
	if err != nil {
		panic("connect FilterCatalogRelease MongoDB: " + err.Error())
	}
	filterCatalogMongoDB = client.Database("content_filter_catalog_release_test")

	code := m.Run()

	_ = client.Disconnect(ctx)
	if mongoContainer != nil {
		_ = mongoContainer.Terminate(ctx)
	}
	os.Exit(code)
}

func requireFilterCatalogMongoDB(tb testing.TB) *mongo.Database {
	tb.Helper()
	if filterCatalogMongoDB == nil {
		tb.Fatal("FilterCatalogRelease api_integration requires TestMain MongoDB")
	}
	return filterCatalogMongoDB
}

func tryRunFilterCatalogMongoContainer(
	ctx context.Context,
) (container *mongomod.MongoDBContainer, err error) {
	defer func() {
		if recovered := recover(); recovered != nil {
			err = fmt.Errorf("testcontainers panic (Docker unavailable?): %v", recovered)
		}
	}()
	return mongomod.Run(ctx, "mongo:7-jammy", mongomod.WithReplicaSet("rs0"))
}
