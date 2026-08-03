package support

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/runtime/operation"
)

// StartRealMongo starts a replica-set-backed Mongo runtime for one object-level
// API contract. Object tests own their collections and assertions; this helper
// only centralizes the external dependency lifecycle and trusted operation
// context used by the production HTTP adapter.
func StartRealMongo(t testing.TB, databaseName string) *mongo.Database {
	t.Helper()
	runtime, err := testinfra.StartRealMongo(context.Background(), databaseName)
	if err != nil {
		t.Fatalf("start real MongoDB for %s: %v", databaseName, err)
	}
	t.Cleanup(func() {
		if err := runtime.Close(context.Background()); err != nil {
			t.Errorf("close real MongoDB for %s: %v", databaseName, err)
		}
	})
	return runtime.Database
}

func Request(
	t testing.TB,
	method string,
	path string,
	body any,
	operationID string,
	personaID string,
	idempotencyKey string,
) *http.Request {
	t.Helper()
	payload := []byte(nil)
	if body != nil {
		var err error
		payload, err = json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal %s request: %v", operationID, err)
		}
	}
	request, err := http.NewRequest(method, path, bytes.NewReader(payload))
	if err != nil {
		t.Fatalf("create %s request: %v", operationID, err)
	}
	request.Header.Set("Content-Type", "application/json")
	request = request.WithContext(operation.WithContext(request.Context(), operation.Context{
		OperationID:    operationID,
		RequestID:      "request-" + idempotencyKey,
		TraceID:        "trace-" + idempotencyKey,
		IdempotencyKey: idempotencyKey,
		SessionID:      "session-" + idempotencyKey,
		Actor: operation.ActorContext{
			AccountID: "account-" + personaID,
			PersonaID: personaID,
		},
	}))
	return request
}

func AssertCollectionCount(t testing.TB, database *mongo.Database, collection string, want int64) {
	t.Helper()
	got, err := database.Collection(collection).CountDocuments(context.Background(), bson.M{})
	if err != nil {
		t.Fatalf("count %s: %v", collection, err)
	}
	if got != want {
		t.Fatalf("%s count=%d want=%d", collection, got, want)
	}
}
