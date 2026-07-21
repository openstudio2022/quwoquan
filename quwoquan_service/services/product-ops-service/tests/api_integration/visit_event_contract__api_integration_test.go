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
	if productOpsEmbeddedPGRuntimePath != "" {
		_ = os.RemoveAll(productOpsEmbeddedPGRuntimePath)
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

// TestVisitRecordIdempotentReplayDoesNotDoubleCount 覆盖 visit_record 契约
// visit_idempotent_replay 与 visit_count_increment 场景：相同 actor+Idempotency-Key
// 的重放回读当前计数，不重复累加；不同 key 的真实访问正常递增。
func TestVisitRecordIdempotentReplayDoesNotDoubleCount(t *testing.T) {
	ctx := context.Background()
	if _, err := telemetryMongoDB.Collection("visit_records").DeleteMany(ctx, bson.D{}); err != nil {
		t.Fatalf("clear visits: %v", err)
	}
	schema := fmt.Sprintf("visit_ledger_test_%d", time.Now().UnixNano())
	ledger, err := telemetrypersistence.NewPostgresTelemetryStore(controlPlanePGPool, schema)
	if err != nil {
		t.Fatalf("new telemetry ledger: %v", err)
	}
	if err := ledger.EnsureSchema(ctx); err != nil {
		t.Fatalf("ensure ledger schema: %v", err)
	}
	t.Cleanup(func() {
		_, _ = controlPlanePGPool.Exec(context.Background(), `DROP SCHEMA "`+schema+`" CASCADE`)
	})
	service := application.NewTelemetryService(realVisitStore, ledger, ledger)

	input := application.VisitInput{
		UserID: "visit-replay-user", TargetType: "page", TargetKey: "circle_detail",
	}
	first, err := service.RecordVisit(ctx, input, "visit-key-1")
	if err != nil || first.VisitCount != 1 || first.Replayed {
		t.Fatalf("first visit result=%+v err=%v", first, err)
	}
	replayed, err := service.RecordVisit(ctx, input, "visit-key-1")
	if err != nil || replayed.VisitCount != 1 || !replayed.Replayed {
		t.Fatalf("idempotent replay must not double count: result=%+v err=%v", replayed, err)
	}
	second, err := service.RecordVisit(ctx, input, "visit-key-2")
	if err != nil || second.VisitCount != 2 || second.Replayed {
		t.Fatalf("distinct key must increment: result=%+v err=%v", second, err)
	}
	if _, err := service.RecordVisit(ctx, input, "  "); err == nil {
		t.Fatal("missing idempotency key must be rejected")
	}
	record, found, err := realVisitStore.GetVisit(ctx, "visit-replay-user", "page", "circle_detail")
	if err != nil || !found || record.VisitCount != 2 {
		t.Fatalf("stored visit count mismatch: record=%+v found=%v err=%v", record, found, err)
	}
}

func TestPostgresTelemetryLocalCompositionUsesTypedPortsAndIsolatableSchema(t *testing.T) {
	ctx := context.Background()
	schema := fmt.Sprintf("telemetry_local_test_%d", time.Now().UnixNano())
	store, err := telemetrypersistence.NewPostgresTelemetryStore(controlPlanePGPool, schema)
	if err != nil {
		t.Fatalf("new postgres telemetry store: %v", err)
	}
	if err := store.EnsureSchema(ctx); err != nil {
		t.Fatalf("ensure telemetry schema: %v", err)
	}
	t.Cleanup(func() {
		_, _ = controlPlanePGPool.Exec(context.Background(), `DROP SCHEMA "`+schema+`" CASCADE`)
	})

	service := application.NewTelemetryService(store, store, store)
	occurredAt := time.Now().UTC().Add(-time.Minute)
	callType := "audio"
	connectTimeMS := 120
	mediaConnected := true
	reconnectCount := 0
	event := application.EventRecordInput{
		LogType:            "event",
		EventType:          "rtc_media_qoe",
		SessionID:          "s.dXNlci0x.1",
		PageName:           "home",
		OccurredAt:         occurredAt.Format(time.RFC3339Nano),
		DeviceManufacturer: "Apple",
		DeviceModel:        "iPhone",
		AppVersion:         "1.0.0",
		NetworkClass:       "wifi",
		DevicePlatform:     "ios",
		CallType:           &callType,
		ConnectTimeMS:      &connectTimeMS,
		MediaConnected:     &mediaConnected,
		ReconnectCount:     &reconnectCount,
	}
	detected := "detected"
	ignored := "ignored"
	event.Result = &detected
	ignoredEvent := event
	ignoredEvent.SessionID = "s.dXNlci0y.1"
	ignoredEvent.Result = &ignored
	if _, err := service.ReportEventBatch(ctx, strings.Repeat("a", 64), []application.EventRecordInput{event, ignoredEvent}); err != nil {
		t.Fatalf("report event batch: %v", err)
	}
	summary, err := service.GetEventSummary(ctx, application.EventSummaryQuery{
		Result: "detected",
		From:   time.Now().UTC().Add(-time.Hour),
		To:     time.Now().UTC().Add(time.Minute),
	})
	if err != nil {
		t.Fatalf("get postgres summary: %v", err)
	}
	if summary.TotalCount != 1 || summary.SessionCount != 1 || summary.SourceKind != "raw_records" {
		t.Fatalf("unexpected postgres summary: %+v", summary)
	}
	drilldown, err := service.GetEventDrilldown(ctx, application.EventDrilldownQuery{
		Result: "detected",
		From:   time.Now().UTC().Add(-time.Hour),
		To:     time.Now().UTC().Add(time.Minute),
		Limit:  10,
	})
	if err != nil {
		t.Fatalf("get postgres drilldown: %v", err)
	}
	if drilldown.TotalCount != 1 || len(drilldown.Items) != 1 {
		t.Fatalf("unexpected postgres drilldown: %+v", drilldown)
	}
}
