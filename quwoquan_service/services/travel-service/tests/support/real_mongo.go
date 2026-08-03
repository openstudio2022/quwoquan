package support

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/internal/platform/testinfra"
)

func StartRealMongo(t *testing.T, databaseName string) *mongo.Database {
	t.Helper()
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	t.Cleanup(cancel)
	runtime, err := testinfra.StartRealMongo(startupCtx, databaseName)
	if err != nil {
		t.Fatalf("start real MongoDB replica set: %v", err)
	}
	t.Cleanup(func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer closeCancel()
		if closeErr := runtime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})
	return runtime.Database
}

func Count(t *testing.T, collection *mongo.Collection, filter any, expected int64) {
	t.Helper()
	count, err := collection.CountDocuments(t.Context(), filter)
	if err != nil || count != expected {
		t.Fatalf("Mongo count=%d want=%d err=%v filter=%#v", count, expected, err, filter)
	}
}
