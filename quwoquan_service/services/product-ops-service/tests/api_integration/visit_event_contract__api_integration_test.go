package api_integration

import (
	"context"
	"fmt"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/services/product-ops-service/internal/application"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/infrastructure/persistence"
)

var (
	telemetryMongoClient    *mongo.Client
	telemetryMongoDB        *mongo.Database
	telemetryMongoContainer *mongomod.MongoDBContainer
	realVisitStore          *telemetrypersistence.MongoVisitStore
	controlPlanePGPool      *pgxpool.Pool
)

func TestMain(m *testing.M) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancelStartup := context.WithTimeout(context.Background(), 2*time.Minute)
	mongoURI := strings.TrimSpace(os.Getenv("TEST_MONGO_URI"))
	if mongoURI == "" {
		container, err := tryRunMongoContainer(startupCtx)
		if err != nil {
			panic("product-ops api_integration requires MongoDB for visit_record: " + err.Error())
		}
		telemetryMongoContainer = container
		uri, err := container.ConnectionString(startupCtx)
		if err != nil {
			panic("get MongoDB connection string: " + err.Error())
		}
		mongoURI = uri + "&directConnection=true"
	}
	var err error
	telemetryMongoClient, err = mongo.Connect(options.Client().ApplyURI(mongoURI).SetConnectTimeout(10 * time.Second).SetServerSelectionTimeout(10 * time.Second))
	if err != nil {
		panic("connect MongoDB: " + err.Error())
	}
	if err := telemetryMongoClient.Ping(startupCtx, nil); err != nil {
		panic("ping MongoDB: " + err.Error())
	}
	telemetryMongoDB = telemetryMongoClient.Database(fmt.Sprintf("product_ops_api_integration_%d", time.Now().UnixNano()))
	realVisitStore = telemetrypersistence.NewMongoVisitStore(telemetryMongoDB)
	if err := realVisitStore.EnsureIndexes(startupCtx); err != nil {
		panic("ensure visit indexes: " + err.Error())
	}

	postgresDSN := strings.TrimSpace(os.Getenv("QWQ_TEST_POSTGRES_DSN"))
	if postgresDSN == "" {
		postgresDSN = strings.TrimSpace(os.Getenv("TEST_PG_DSN"))
	}
	if postgresDSN == "" {
		postgresDSN = startProductOpsEmbeddedPostgres()
	}
	controlPlanePGPool, err = pgxpool.New(startupCtx, postgresDSN)
	if err != nil {
		panic("connect PostgreSQL: " + err.Error())
	}
	if err := controlPlanePGPool.Ping(startupCtx); err != nil {
		panic("ping PostgreSQL: " + err.Error())
	}
	cancelStartup()

	code := m.Run()
	cleanupCtx, cancelCleanup := context.WithTimeout(context.Background(), 30*time.Second)
	_ = telemetryMongoDB.Drop(cleanupCtx)
	_ = telemetryMongoClient.Disconnect(cleanupCtx)
	controlPlanePGPool.Close()
	if telemetryMongoContainer != nil {
		_ = telemetryMongoContainer.Terminate(cleanupCtx)
	}
	if productOpsEmbeddedPG != nil {
		_ = productOpsEmbeddedPG.Stop()
	}
	cancelCleanup()
	os.Exit(code)
}

func tryRunMongoContainer(ctx context.Context) (container *mongomod.MongoDBContainer, err error) {
	defer func() {
		if recovered := recover(); recovered != nil {
			err = fmt.Errorf("testcontainers panic: %v", recovered)
		}
	}()
	return mongomod.Run(ctx, "mongo:7-jammy", mongomod.WithReplicaSet("rs0"))
}

func TestMongoVisitStoreKeepsVisitFactWithoutEventCollection(t *testing.T) {
	ctx := context.Background()
	if _, err := telemetryMongoDB.Collection("visit_records").DeleteMany(ctx, bson.D{}); err != nil {
		t.Fatalf("clear visits: %v", err)
	}
	for range 2 {
		if _, err := realVisitStore.RecordVisit(ctx, application.VisitInput{
			UserID: "user-1", TargetType: "page", TargetKey: "home", SessionID: "s.dXNlci0x.1",
		}); err != nil {
			t.Fatalf("record visit: %v", err)
		}
	}
	stats, err := realVisitStore.GetVisitStats(ctx, application.VisitStatsQuery{TargetType: "page", TargetKey: "home"})
	if err != nil || stats.TotalVisits != 2 || len(stats.Items) != 1 {
		t.Fatalf("visit stats=%+v err=%v", stats, err)
	}
	names, err := telemetryMongoDB.ListCollectionNames(ctx, bson.D{{Key: "name", Value: "event_records"}})
	if err != nil {
		t.Fatalf("list collections: %v", err)
	}
	if len(names) != 0 {
		t.Fatalf("event_records must not be recreated: %v", names)
	}
}
