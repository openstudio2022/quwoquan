// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/event-schema-governance/spec.md#gwt-001
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	visithttp "quwoquan_service/services/product-ops-service/internal/product_ops/visit_record/adapters/inbound/http"
	visitapplication "quwoquan_service/services/product-ops-service/internal/product_ops/visit_record/application"
	visitpersistence "quwoquan_service/services/product-ops-service/internal/product_ops/visit_record/infrastructure/persistence"
)

var (
	visitMongoClient    *mongo.Client
	visitMongoDB        *mongo.Database
	visitMongoContainer *mongomod.MongoDBContainer
	realVisitStore      *visitpersistence.MongoVisitStore
)

func TestMain(m *testing.M) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancelStartup := context.WithTimeout(context.Background(), 2*time.Minute)
	mongoURI := strings.TrimSpace(os.Getenv("TEST_MONGO_URI"))
	if mongoURI == "" {
		container, err := tryRunMongoContainer(startupCtx)
		if err != nil {
			panic("product-ops VisitRecord api_integration requires MongoDB: " + err.Error())
		}
		visitMongoContainer = container
		uri, err := container.ConnectionString(startupCtx)
		if err != nil {
			panic("get MongoDB connection string: " + err.Error())
		}
		mongoURI = uri + "&directConnection=true"
	}
	var err error
	visitMongoClient, err = mongo.Connect(options.Client().ApplyURI(mongoURI).
		SetConnectTimeout(10 * time.Second).
		SetServerSelectionTimeout(10 * time.Second))
	if err != nil {
		panic("connect MongoDB: " + err.Error())
	}
	if err := visitMongoClient.Ping(startupCtx, nil); err != nil {
		panic("ping MongoDB: " + err.Error())
	}
	visitMongoDB = visitMongoClient.Database(
		fmt.Sprintf("product_ops_visit_api_%d", time.Now().UnixNano()),
	)
	realVisitStore = visitpersistence.NewMongoVisitStore(visitMongoDB)
	if err := realVisitStore.EnsureIndexes(startupCtx); err != nil {
		panic("ensure VisitRecord indexes: " + err.Error())
	}
	cancelStartup()

	code := m.Run()
	cleanupCtx, cancelCleanup := context.WithTimeout(context.Background(), 30*time.Second)
	_ = visitMongoDB.Drop(cleanupCtx)
	_ = visitMongoClient.Disconnect(cleanupCtx)
	if visitMongoContainer != nil {
		_ = visitMongoContainer.Terminate(cleanupCtx)
	}
	cancelCleanup()
	os.Exit(code)
}

func tryRunMongoContainer(
	ctx context.Context,
) (container *mongomod.MongoDBContainer, err error) {
	defer func() {
		if recovered := recover(); recovered != nil {
			err = fmt.Errorf("testcontainers panic: %v", recovered)
		}
	}()
	return mongomod.Run(ctx, "mongo:7-jammy", mongomod.WithReplicaSet("rs0"))
}

func TestVisitRecordHTTPUsesMongoAtomicReceiptAndTypedErrors(t *testing.T) {
	clearVisitCollections(t)
	handler := visithttp.NewHandler(visitapplication.NewService(realVisitStore))
	mux := http.NewServeMux()
	handler.Register(mux)

	first := performVisitRequest(t, mux, http.MethodPost, "/ops/visits",
		`{"targetType":"page","targetKey":"circle_detail"}`,
		"visit-http-key-1", "persona-http")
	if first.Code != http.StatusOK {
		t.Fatalf("first status=%d body=%s", first.Code, first.Body.String())
	}
	var firstResult visitapplication.CommandResult
	decodeResponse(t, first, &firstResult)
	if firstResult.VisitCount != 1 || firstResult.Replayed || firstResult.OccurredAt.IsZero() {
		t.Fatalf("unexpected first result: %+v", firstResult)
	}

	replay := performVisitRequest(t, mux, http.MethodPost, "/ops/visits",
		`{"targetType":"page","targetKey":"circle_detail"}`,
		"visit-http-key-1", "persona-http")
	if replay.Code != http.StatusOK {
		t.Fatalf("replay status=%d body=%s", replay.Code, replay.Body.String())
	}
	var replayResult visitapplication.CommandResult
	decodeResponse(t, replay, &replayResult)
	if replayResult.VisitCount != 1 || !replayResult.Replayed ||
		!replayResult.OccurredAt.Equal(firstResult.OccurredAt) {
		t.Fatalf("replay changed the first receipt: first=%+v replay=%+v", firstResult, replayResult)
	}

	conflict := performVisitRequest(t, mux, http.MethodPost, "/ops/visits",
		`{"targetType":"page","targetKey":"other_page"}`,
		"visit-http-key-1", "persona-http")
	assertRuntimeError(t, conflict, http.StatusConflict, "OPS.USER.visit_idempotency_conflict")

	second := performVisitRequest(t, mux, http.MethodPost, "/ops/visits",
		`{"targetType":"page","targetKey":"circle_detail"}`,
		"visit-http-key-2", "persona-http")
	if second.Code != http.StatusOK {
		t.Fatalf("second status=%d body=%s", second.Code, second.Body.String())
	}
	var secondResult visitapplication.CommandResult
	decodeResponse(t, second, &secondResult)
	if secondResult.VisitCount != 2 || secondResult.Replayed {
		t.Fatalf("distinct command must increment once: %+v", secondResult)
	}

	stats := performVisitRequest(t, mux, http.MethodGet,
		"/ops/visits/stats?targetType=page&targetKey=circle_detail", "", "", "persona-http")
	if stats.Code != http.StatusOK {
		t.Fatalf("stats status=%d body=%s", stats.Code, stats.Body.String())
	}
	var statsResult visitapplication.VisitStats
	decodeResponse(t, stats, &statsResult)
	if statsResult.TotalVisits != 2 || len(statsResult.Items) != 1 ||
		statsResult.Items[0].UserID != "" {
		t.Fatalf("stats must aggregate without exposing actor: %+v", statsResult)
	}
	if strings.Contains(stats.Body.String(), "userId") {
		t.Fatalf("stats wire leaked actor identifier: %s", stats.Body.String())
	}

	spoof := performVisitRequest(t, mux, http.MethodPost, "/ops/visits",
		`{"targetType":"page","targetKey":"home","userId":"attacker"}`,
		"visit-http-key-3", "persona-http")
	assertRuntimeError(t, spoof, http.StatusBadRequest, "OPS.USER.visit_invalid_argument")
	unauthorized := performVisitRequest(t, mux, http.MethodPost, "/ops/visits",
		`{"targetType":"page","targetKey":"home"}`, "visit-http-key-4", "")
	assertRuntimeError(t, unauthorized, http.StatusUnauthorized, "GATEWAY.USER.unauthorized")

	assertCollectionCount(t, "visit_records", bson.D{}, 1)
	assertCollectionCount(t, "visit_record_command_receipts", bson.D{}, 2)
	assertCollectionAbsent(t, "visit_record_outbox")
	assertCollectionAbsent(t, "event_records")
}

func TestVisitRecordConcurrentReplayIncrementsExactlyOnce(t *testing.T) {
	clearVisitCollections(t)
	service := visitapplication.NewService(realVisitStore)
	input := visitapplication.VisitInput{
		UserID:     "actor-concurrent",
		TargetType: "post",
		TargetKey:  "post-1",
	}
	const requests = 12
	var wg sync.WaitGroup
	var failures atomic.Int64
	results := make(chan visitapplication.CommandResult, requests)
	for range requests {
		wg.Add(1)
		go func() {
			defer wg.Done()
			result, err := service.RecordVisit(context.Background(), input, "same-key")
			if err != nil {
				failures.Add(1)
				return
			}
			results <- result
		}()
	}
	wg.Wait()
	close(results)
	if failures.Load() != 0 {
		t.Fatalf("concurrent replay failures=%d", failures.Load())
	}
	for result := range results {
		if result.VisitCount != 1 {
			t.Fatalf("concurrent replay returned non-first receipt: %+v", result)
		}
	}
	record, found, err := realVisitStore.GetVisit(
		context.Background(), "actor-concurrent", "post", "post-1",
	)
	if err != nil || !found || record.VisitCount != 1 {
		t.Fatalf("atomic visit mismatch: record=%+v found=%v err=%v", record, found, err)
	}
	assertCollectionCount(t, "visit_record_command_receipts", bson.D{}, 1)

	if _, err := service.RecordVisit(context.Background(), visitapplication.VisitInput{
		UserID: "actor-concurrent", TargetType: "post", TargetKey: "post-2",
	}, "same-key"); err != visitapplication.ErrIdempotencyConflict {
		t.Fatalf("same actor/key with another target error=%v", err)
	}
	assertCollectionCount(t, "visit_records", bson.D{}, 1)
}

func performVisitRequest(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	body string,
	idempotencyKey string,
	personaID string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(method, path, bytes.NewBufferString(body))
	request.Header.Set("X-Request-Id", "visit-request-id")
	request.Header.Set("X-Trace-Id", "visit-trace-id")
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	if personaID != "" {
		request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
			Actor: operation.ActorContext{PersonaID: personaID},
		}))
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func assertRuntimeError(
	t *testing.T,
	recorder *httptest.ResponseRecorder,
	status int,
	code string,
) {
	t.Helper()
	if recorder.Code != status {
		t.Fatalf("status=%d want=%d body=%s", recorder.Code, status, recorder.Body.String())
	}
	var response struct {
		Code      string `json:"code"`
		RequestID string `json:"requestId"`
		TraceID   string `json:"traceId"`
	}
	decodeResponse(t, recorder, &response)
	if response.Code != code || response.RequestID != "visit-request-id" ||
		response.TraceID != "visit-trace-id" {
		t.Fatalf("typed error mismatch: %+v body=%s", response, recorder.Body.String())
	}
}

func decodeResponse(t *testing.T, recorder *httptest.ResponseRecorder, target any) {
	t.Helper()
	if err := json.Unmarshal(recorder.Body.Bytes(), target); err != nil {
		t.Fatalf("decode response %s: %v", recorder.Body.String(), err)
	}
}

func clearVisitCollections(t *testing.T) {
	t.Helper()
	ctx := context.Background()
	for _, name := range []string{"visit_records", "visit_record_command_receipts"} {
		if _, err := visitMongoDB.Collection(name).DeleteMany(ctx, bson.D{}); err != nil {
			t.Fatalf("clear %s: %v", name, err)
		}
	}
}

func assertCollectionCount(t *testing.T, name string, filter any, want int64) {
	t.Helper()
	count, err := visitMongoDB.Collection(name).CountDocuments(context.Background(), filter)
	if err != nil || count != want {
		t.Fatalf("%s count=%d want=%d err=%v", name, count, want, err)
	}
}

func assertCollectionAbsent(t *testing.T, name string) {
	t.Helper()
	names, err := visitMongoDB.ListCollectionNames(
		context.Background(), bson.D{{Key: "name", Value: name}},
	)
	if err != nil {
		t.Fatalf("list collection %s: %v", name, err)
	}
	if len(names) != 0 {
		t.Fatalf("retired collection %s exists", name)
	}
}
