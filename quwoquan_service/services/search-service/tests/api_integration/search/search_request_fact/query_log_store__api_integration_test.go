package api_integration

import (
	"context"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/search-service/internal/search/search_request_fact/application"
	"quwoquan_service/services/search-service/internal/search/search_request_fact/infrastructure/querylogstore"
)

func TestQueryLogUpsertIdempotent(t *testing.T) {
	cleanSearchCollections(t)
	store := querylogstore.NewStore(mongoDB)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure query log indexes: %v", err)
	}
	query := application.QueryLog{
		SearchRequestID: "req-log-1",
		Query:           "chengdu",
		Mode:            "result",
		ResultCount:     7,
	}
	if err := store.Log(context.Background(), query); err != nil {
		t.Fatalf("first log: %v", err)
	}
	query.ResultCount = 9
	if err := store.Log(context.Background(), query); err != nil {
		t.Fatalf("retry log: %v", err)
	}
	count, err := mongoDB.Collection("search_queries").CountDocuments(
		context.Background(),
		bson.M{"searchRequestId": query.SearchRequestID},
	)
	if err != nil || count != 1 {
		t.Fatalf("query log count=%d err=%v", count, err)
	}
}
