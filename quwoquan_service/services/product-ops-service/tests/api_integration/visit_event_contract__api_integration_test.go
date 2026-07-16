package api_integration

import (
	"context"
	"errors"
	"fmt"
	"os"
	"strings"
	"sync"
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
	realTelemetryStore      *telemetrypersistence.MongoTelemetryStore
	controlPlanePGPool      *pgxpool.Pool
)

func TestMain(m *testing.M) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancelStartup := context.WithTimeout(context.Background(), 2*time.Minute)
	mongoURI := strings.TrimSpace(os.Getenv("TEST_MONGO_URI"))
	if mongoURI == "" {
		container, err := tryRunMongoContainer(startupCtx)
		if err != nil {
			panic(
				"product-ops-service api_integration requires a real MongoDB; " +
					"set TEST_MONGO_URI or start Docker: " + err.Error(),
			)
		}
		telemetryMongoContainer = container
		uri, err := container.ConnectionString(startupCtx)
		if err != nil {
			panic("get MongoDB testcontainer connection string: " + err.Error())
		}
		mongoURI = uri + "&directConnection=true"
	}

	var err error
	telemetryMongoClient, err = mongo.Connect(
		options.Client().
			ApplyURI(mongoURI).
			SetConnectTimeout(10 * time.Second).
			SetServerSelectionTimeout(10 * time.Second),
	)
	if err != nil {
		panic("connect product-ops api_integration MongoDB: " + err.Error())
	}
	if err := telemetryMongoClient.Ping(startupCtx, nil); err != nil {
		panic("ping product-ops api_integration MongoDB: " + err.Error())
	}
	telemetryMongoDB = telemetryMongoClient.Database(
		fmt.Sprintf("product_ops_api_integration_%d", time.Now().UnixNano()),
	)
	realTelemetryStore = telemetrypersistence.NewMongoTelemetryStore(telemetryMongoDB)
	if err := realTelemetryStore.EnsureIndexes(startupCtx); err != nil {
		panic("ensure product-ops telemetry indexes: " + err.Error())
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
		panic("connect product-ops api_integration PostgreSQL: " + err.Error())
	}
	if err := controlPlanePGPool.Ping(startupCtx); err != nil {
		panic("ping product-ops api_integration PostgreSQL: " + err.Error())
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
			err = fmt.Errorf("testcontainers panic (Docker unavailable?): %v", recovered)
		}
	}()
	return mongomod.Run(ctx, "mongo:7-jammy", mongomod.WithReplicaSet("rs0"))
}

func resetTelemetryCollections(t *testing.T) {
	t.Helper()
	if realTelemetryStore == nil || telemetryMongoDB == nil {
		t.Fatal("real MongoDB telemetry store was not initialized")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	for _, collection := range []string{"visit_records", "event_records"} {
		if _, err := telemetryMongoDB.Collection(collection).DeleteMany(ctx, bson.D{}); err != nil {
			t.Fatalf("clean %s: %v", collection, err)
		}
	}
}

type failingMirror struct {
	called chan struct{}
}

func (m failingMirror) MirrorEvents(context.Context, []application.EventDrilldownItem) error {
	close(m.called)
	return errors.New("es unavailable")
}

func TestMongoTelemetryStore_RequiredIndexes(t *testing.T) {
	required := map[string]struct{}{
		"idx_event_event_id":       {},
		"idx_event_type_name_time": {},
		"idx_event_session_time":   {},
		"ttl_event_expires_at":     {},
		"ttl_event_occurred_at":    {},
		"uq_visit_user_target":     {},
		"idx_visit_user_target":    {},
		"idx_visit_target":         {},
		"idx_visit_session":        {},
		"ttl_visit_timestamp":      {},
	}
	found := map[string]bson.M{}
	for _, collection := range []string{"event_records", "visit_records"} {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		cursor, err := telemetryMongoDB.Collection(collection).Indexes().List(ctx)
		if err != nil {
			cancel()
			t.Fatalf("list %s indexes: %v", collection, err)
		}
		var indexes []bson.M
		if err := cursor.All(ctx, &indexes); err != nil {
			cancel()
			t.Fatalf("decode %s indexes: %v", collection, err)
		}
		cancel()
		for _, index := range indexes {
			if name, _ := index["name"].(string); name != "" {
				if _, ok := required[name]; ok {
					found[name] = index
				}
			}
		}
	}
	for name := range required {
		if found[name] == nil {
			t.Errorf("required telemetry index %q was not created", name)
		}
	}
	if unique, _ := found["idx_event_event_id"]["unique"].(bool); !unique {
		t.Errorf("idx_event_event_id must be unique: %+v", found["idx_event_event_id"])
	}
	if unique, _ := found["uq_visit_user_target"]["unique"].(bool); !unique {
		t.Errorf("uq_visit_user_target must be unique: %+v", found["uq_visit_user_target"])
	}
	assertExpireAfterSeconds(t, found["ttl_event_occurred_at"], 90*24*60*60)
	assertExpireAfterSeconds(t, found["ttl_event_expires_at"], 0)
	assertExpireAfterSeconds(t, found["ttl_visit_timestamp"], 180*24*60*60)
}

func assertExpireAfterSeconds(t *testing.T, index bson.M, want int64) {
	t.Helper()
	var got int64
	switch value := index["expireAfterSeconds"].(type) {
	case int32:
		got = int64(value)
	case int64:
		got = value
	default:
		t.Fatalf("index missing numeric expireAfterSeconds: %+v", index)
	}
	if got != want {
		t.Fatalf("expireAfterSeconds=%d, want %d: %+v", got, want, index)
	}
}

func TestTelemetryStore_RecordVisitAndStats(t *testing.T) {
	resetTelemetryCollections(t)
	ctx := context.Background()
	for range 3 {
		if _, err := realTelemetryStore.RecordVisit(ctx, application.VisitInput{
			UserID:     "user-1",
			TargetType: "page",
			TargetKey:  "page_home",
			SessionID:  "sess_1",
			Source:     "page_access",
		}); err != nil {
			t.Fatalf("record visit: %v", err)
		}
	}

	reopenedStore := telemetrypersistence.NewMongoTelemetryStore(telemetryMongoDB)
	stats, err := reopenedStore.GetVisitStats(ctx, application.VisitStatsQuery{
		TargetType: "page",
		TargetKey:  "page_home",
	})
	if err != nil {
		t.Fatalf("get visit stats: %v", err)
	}
	if stats.TotalVisits != 3 {
		t.Fatalf("expected totalVisits=3, got %d", stats.TotalVisits)
	}
	if len(stats.Items) != 1 || stats.Items[0].VisitCount != 3 {
		t.Fatalf("unexpected visit stats: %+v", stats.Items)
	}
	count, err := telemetryMongoDB.Collection("visit_records").CountDocuments(ctx, bson.D{
		{Key: "userId", Value: "user-1"},
		{Key: "targetType", Value: "page"},
		{Key: "targetKey", Value: "page_home"},
	})
	if err != nil {
		t.Fatalf("count persisted visits: %v", err)
	}
	if count != 1 {
		t.Fatalf("visit upsert must keep one authoritative row, got %d", count)
	}
	var persisted bson.M
	if err := telemetryMongoDB.Collection("visit_records").FindOne(ctx, bson.D{
		{Key: "userId", Value: "user-1"},
	}).Decode(&persisted); err != nil {
		t.Fatalf("read persisted visit: %v", err)
	}
	if _, ok := persisted["timestamp"].(bson.DateTime); !ok {
		t.Fatalf("visit timestamp must be a BSON date for TTL retention: %T", persisted["timestamp"])
	}
}

func TestTelemetryStore_ReportEventBatchIdempotentSummaryAndDrilldown(t *testing.T) {
	resetTelemetryCollections(t)
	ctx := context.Background()
	events := []application.EventRecordInput{
		{
			EventID:          "evt-1",
			EventType:        "experience",
			EventName:        "page_open",
			EventVersion:     "v1",
			Priority:         "P0",
			Producer:         "app.page_access",
			PageName:         "home",
			SurfaceID:        "home_feed",
			ExperimentBucket: "control",
			Source:           "page_access",
			OccurredAt:       "2026-04-01T00:00:00Z",
		},
		{
			EventID:          "evt-2",
			EventType:        "experience",
			EventName:        "page_open",
			EventVersion:     "v1",
			Priority:         "P0",
			Producer:         "app.page_access",
			PageName:         "home",
			SurfaceID:        "home_feed",
			ExperimentBucket: "treatment",
			Source:           "page_access",
			OccurredAt:       "2026-04-01T00:00:05Z",
		},
	}

	ack1, _, err := realTelemetryStore.ReportEventBatch(ctx, events)
	if err != nil {
		t.Fatalf("report first batch: %v", err)
	}
	ack2, _, err := realTelemetryStore.ReportEventBatch(ctx, events[:1])
	if err != nil {
		t.Fatalf("report duplicate batch: %v", err)
	}
	if ack1.AcceptedCount != 2 || ack2.DuplicateCount != 1 {
		t.Fatalf("unexpected batch ack: first=%+v second=%+v", ack1, ack2)
	}
	count, err := telemetryMongoDB.Collection("event_records").CountDocuments(
		ctx,
		bson.D{{Key: "eventId", Value: "evt-1"}},
	)
	if err != nil {
		t.Fatalf("count persisted events: %v", err)
	}
	if count != 1 {
		t.Fatalf("eventId unique index must keep one authoritative row, got %d", count)
	}
	var persisted bson.M
	if err := telemetryMongoDB.Collection("event_records").FindOne(
		ctx,
		bson.D{{Key: "eventId", Value: "evt-1"}},
	).Decode(&persisted); err != nil {
		t.Fatalf("read persisted event: %v", err)
	}
	if _, ok := persisted["occurredAt"].(bson.DateTime); !ok {
		t.Fatalf("event occurredAt must be a BSON date for TTL retention: %T", persisted["occurredAt"])
	}
	if _, ok := persisted["expiresAt"].(bson.DateTime); !ok {
		t.Fatalf("event expiresAt must be a BSON date for per-event TTL retention: %T", persisted["expiresAt"])
	}

	reopenedStore := telemetrypersistence.NewMongoTelemetryStore(telemetryMongoDB)
	summary, err := reopenedStore.GetEventSummary(ctx, application.EventSummaryQuery{
		EventType: "experience",
		EventName: "page_open",
		PageName:  "home",
		Source:    "page_access",
		From:      time.Date(2026, 4, 1, 0, 0, 0, 0, time.UTC),
		To:        time.Date(2026, 4, 1, 0, 0, 10, 0, time.UTC),
	})
	if err != nil {
		t.Fatalf("get event summary: %v", err)
	}
	if summary.TotalCount != 2 ||
		summary.DimensionCounters["pageName"]["home"] != 2 ||
		summary.DimensionCounters["experimentBucket"]["control"] != 1 ||
		summary.DimensionCounters["experimentBucket"]["treatment"] != 1 {
		t.Fatalf("unexpected event summary: %+v", summary)
	}
	if summary.LatestOccurredAt != "2026-04-01T00:00:05Z" {
		t.Fatalf("unexpected latest occurredAt: %q", summary.LatestOccurredAt)
	}

	drilldown, err := reopenedStore.GetEventDrilldown(ctx, application.EventDrilldownQuery{
		EventType: "experience",
		EventName: "page_open",
		Limit:     1,
	})
	if err != nil {
		t.Fatalf("get event drilldown: %v", err)
	}
	if drilldown.TotalCount != 2 || len(drilldown.Items) != 1 || drilldown.Items[0].EventID != "evt-2" {
		t.Fatalf("drilldown must return full count and limited newest item, got %+v", drilldown)
	}
}

func TestTelemetryStore_ReportEventBatchConcurrentEventIDIdempotency(t *testing.T) {
	resetTelemetryCollections(t)
	const writers = 8
	event := application.EventRecordInput{
		EventID:      "evt-concurrent",
		EventType:    "experience",
		EventName:    "page_open",
		EventVersion: "v1",
		Priority:     "P0",
		Producer:     "app.page_access",
		PageName:     "home",
		OccurredAt:   "2026-04-01T00:00:00Z",
	}

	type result struct {
		ack application.EventBatchAck
		err error
	}
	results := make(chan result, writers)
	var waitGroup sync.WaitGroup
	for range writers {
		waitGroup.Add(1)
		go func() {
			defer waitGroup.Done()
			ack, _, err := realTelemetryStore.ReportEventBatch(
				context.Background(),
				[]application.EventRecordInput{event},
			)
			results <- result{ack: ack, err: err}
		}()
	}
	waitGroup.Wait()
	close(results)

	accepted := 0
	duplicates := 0
	for item := range results {
		if item.err != nil {
			t.Fatalf("concurrent event report failed: %v", item.err)
		}
		accepted += item.ack.AcceptedCount
		duplicates += item.ack.DuplicateCount
	}
	if accepted != 1 || duplicates != writers-1 {
		t.Fatalf("concurrent idempotency ack accepted=%d duplicates=%d", accepted, duplicates)
	}
	count, err := telemetryMongoDB.Collection("event_records").CountDocuments(
		context.Background(),
		bson.D{{Key: "eventId", Value: event.EventID}},
	)
	if err != nil {
		t.Fatalf("count concurrent event: %v", err)
	}
	if count != 1 {
		t.Fatalf("concurrent eventId must persist once, got %d rows", count)
	}
}

func TestTelemetryService_ExceptionMirrorFailureDoesNotBlockAuthoritativeStore(t *testing.T) {
	resetTelemetryCollections(t)
	mirror := failingMirror{called: make(chan struct{})}
	service := application.NewTelemetryServiceWithMirror(realTelemetryStore, nil, mirror)

	ack, err := service.ReportEventBatch(context.Background(), []application.EventRecordInput{
		{
			EventID:        "evt-exception-1",
			EventType:      "exception",
			EventName:      "runtime_exception",
			Producer:       "app.exception",
			SessionID:      "sess-1",
			PageVisitID:    "visit-1",
			RequestID:      "req-1",
			TraceID:        "trace-1",
			PageName:       "global.app.runtime",
			ErrorCode:      "APP.RUNTIME.uncaught_exception",
			ErrorModule:    "APP",
			ErrorKind:      "RUNTIME",
			ErrorReason:    "uncaught_exception",
			Nature:         "bug",
			BusinessObject: "app_runtime",
			FunctionModule: "global_error_handler",
			AppRuntimeEnv:  "alpha",
			AppVersion:     "test",
			Platform:       "ios",
			OccurredAt:     "2026-04-01T00:00:00Z",
		},
	})
	if err != nil {
		t.Fatalf("report event batch should not fail on mirror error: %v", err)
	}
	if ack.AcceptedCount != 1 {
		t.Fatalf("expected accepted count 1, got %+v", ack)
	}
	select {
	case <-mirror.called:
	case <-time.After(time.Second):
		t.Fatal("mirror was not called")
	}
	persisted, err := telemetrypersistence.NewMongoTelemetryStore(telemetryMongoDB).GetEventDrilldown(
		context.Background(),
		application.EventDrilldownQuery{EventName: "runtime_exception", Limit: 10},
	)
	if err != nil {
		t.Fatalf("read authoritative event after mirror failure: %v", err)
	}
	if persisted.TotalCount != 1 || len(persisted.Items) != 1 ||
		persisted.Items[0].EventID != "evt-exception-1" {
		t.Fatalf("mirror failure must not roll back authoritative Mongo event: %+v", persisted)
	}
}
