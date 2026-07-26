package querylogstore

import (
	"context"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/search-service/internal/search/search_query/application"
)

const QueriesTTLSeconds = 7776000

type Store struct {
	queries *mongo.Collection
}

var _ application.QueryLogSink = (*Store)(nil)

func NewStore(db *mongo.Database) *Store {
	return &Store{queries: db.Collection("search_queries")}
}

func (s *Store) EnsureIndexes(ctx context.Context) error {
	if _, err := s.queries.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{{Key: "searchRequestId", Value: 1}},
			Options: options.Index().
				SetUnique(true).
				SetName("idx_search_queries_request"),
		},
		{
			Keys: bson.D{{Key: "createdAt", Value: -1}},
			Options: options.Index().
				SetName("idx_search_queries_created").
				SetExpireAfterSeconds(int32(QueriesTTLSeconds)),
		},
		{
			Keys: bson.D{
				{Key: "query", Value: 1},
				{Key: "createdAt", Value: -1},
			},
			Options: options.Index().
				SetName("idx_search_queries_query_created"),
		},
	}); err != nil {
		return fmt.Errorf("ensure search query indexes: %w", err)
	}
	return nil
}

func (s *Store) Log(
	ctx context.Context,
	query application.QueryLog,
) error {
	now := time.Now().UTC()
	document := bson.M{
		"searchRequestId":  query.SearchRequestID,
		"query":            query.Query,
		"mode":             query.Mode,
		"viewerId":         query.ViewerID,
		"objectTypes":      query.ObjectTypes,
		"resultCount":      query.ResultCount,
		"rankingVersion":   query.RankingVersion,
		"experimentBucket": query.ExperimentBucket,
	}
	_, err := s.queries.UpdateOne(
		ctx,
		bson.M{"searchRequestId": query.SearchRequestID},
		bson.M{
			"$set": document,
			"$setOnInsert": bson.M{
				"createdAt": now,
			},
		},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}
