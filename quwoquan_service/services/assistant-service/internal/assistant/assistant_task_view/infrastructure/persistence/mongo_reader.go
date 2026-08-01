package persistence

import (
	"context"
	"errors"

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
