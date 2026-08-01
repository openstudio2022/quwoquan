package skill_package_release_integration

import (
	"context"
	"os"
	"strconv"
	"strings"
	"testing"
	"time"

	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/internal/platform/testinfra"
)

var (
	skillPackageDB        *mongo.Database
	skillPackageClient    *mongo.Client
	skillPackageContainer *mongomod.MongoDBContainer
)

func TestMain(m *testing.M) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	testinfra.ConfigureLocalContainerRuntime()
	startSkillPackageMongo(ctx)
	cancel()

	code := m.Run()

	shutdownCtx, shutdownCancel := context.WithTimeout(
		context.Background(),
		45*time.Second,
	)
	if skillPackageDB != nil {
		_ = skillPackageDB.Drop(shutdownCtx)
	}
	if skillPackageClient != nil {
		_ = skillPackageClient.Disconnect(shutdownCtx)
	}
	if skillPackageContainer != nil {
		_ = skillPackageContainer.Terminate(shutdownCtx)
	}
	shutdownCancel()
	os.Exit(code)
}

func startSkillPackageMongo(ctx context.Context) {
	mongoURI := strings.TrimSpace(os.Getenv("QWQ_TEST_MONGO_URI"))
	if mongoURI == "" {
		mongoURI = strings.TrimSpace(os.Getenv("TEST_MONGO_URI"))
	}
	if mongoURI == "" {
		container, err := mongomod.Run(
			ctx,
			"mongo:7-jammy",
			mongomod.WithReplicaSet("rs0"),
		)
		if err != nil {
			panic("skill package api_integration requires real MongoDB: " + err.Error())
		}
		skillPackageContainer = container
		mongoURI, err = container.ConnectionString(ctx)
		if err != nil {
			panic("skill package MongoDB connection string: " + err.Error())
		}
	}
	clientOptions := options.Client().
		ApplyURI(mongoURI).
		SetServerSelectionTimeout(15 * time.Second)
	if skillPackageContainer != nil {
		clientOptions.SetDirect(true)
	}
	var err error
	skillPackageClient, err = mongo.Connect(clientOptions)
	if err != nil {
		panic("skill package connect MongoDB: " + err.Error())
	}
	if err := skillPackageClient.Ping(ctx, nil); err != nil {
		panic("skill package ping MongoDB: " + err.Error())
	}
	skillPackageDB = skillPackageClient.Database(
		"assistant_skill_package_api_integration_" + strconv.Itoa(os.Getpid()),
	)
}
