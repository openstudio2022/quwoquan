package persistence

import (
	"context"
	"errors"
	"fmt"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	taskmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/domain/model"
)

type MongoReader struct{ collection *mongo.Collection }

func NewMongoReader(database *mongo.Database) *MongoReader {
	if database == nil {
		return &MongoReader{}
	}
	return &MongoReader{collection: database.Collection("rm_assistant_tasks")}
}

func (r *MongoReader) EnsureIndexes(ctx context.Context) error {
	if r == nil || r.collection == nil {
		return errors.New("assistant task projection store is unavailable")
	}
	_, err := r.collection.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{{Key: "accountId", Value: 1}, {Key: "taskId", Value: 1}},
			Options: options.Index().
				SetName("uq_assistant_task_account_task").
				SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "accountId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "updatedAt", Value: -1},
			},
			Options: options.Index().SetName("idx_assistant_task_account_status_updated"),
		},
	})
	if err != nil {
		return fmt.Errorf("ensure assistant task projection indexes: %w", err)
	}
	return nil
}

func (r *MongoReader) List(ctx context.Context, accountID, status string, limit int) ([]taskmodel.Item, error) {
	if r == nil || r.collection == nil {
		return nil, errors.New("assistant task projection store is unavailable")
	}
	filter := bson.M{"accountId": accountID}
	if status != "" {
		filter["status"] = status
	}
	cursor, err := r.collection.Find(ctx, filter, options.Find().SetSort(bson.D{{Key: "updatedAt", Value: -1}, {Key: "taskId", Value: 1}}).SetLimit(int64(limit)))
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	items := []taskmodel.Item{}
	if err := cursor.All(ctx, &items); err != nil {
		return nil, err
	}
	return items, nil
}
