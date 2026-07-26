package persistence

import (
	"context"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

func collectCircleIDs(
	ctx context.Context,
	collection *mongo.Collection,
	filter bson.M,
	target map[string]struct{},
) error {
	rows, err := collection.Find(
		ctx,
		filter,
		options.Find().SetProjection(bson.M{"circleId": 1, "_id": 1}),
	)
	if err != nil {
		return err
	}
	defer rows.Close(ctx)
	for rows.Next(ctx) {
		var document struct {
			ID       string `bson:"_id"`
			CircleID string `bson:"circleId"`
		}
		if err := rows.Decode(&document); err != nil {
			return err
		}
		circleID := strings.TrimSpace(document.CircleID)
		if collection.Name() == "circles" {
			circleID = strings.TrimSpace(document.ID)
		}
		if circleID != "" {
			target[circleID] = struct{}{}
		}
	}
	return rows.Err()
}

func collectStringValues(
	ctx context.Context,
	collection *mongo.Collection,
	filter bson.M,
	field string,
) ([]string, error) {
	rows, err := collection.Find(
		ctx,
		filter,
		options.Find().SetProjection(bson.M{field: 1}),
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close(ctx)
	values := make([]string, 0)
	for rows.Next(ctx) {
		var document bson.M
		if err := rows.Decode(&document); err != nil {
			return nil, err
		}
		value, _ := document[field].(string)
		if value = strings.TrimSpace(value); value != "" {
			values = append(values, value)
		}
	}
	return values, rows.Err()
}

func updateReceiptsByAggregateIDs(
	ctx context.Context,
	collection *mongo.Collection,
	field string,
	values []string,
	set bson.M,
) error {
	for start := 0; start < len(values); start += accountClosureMongoBatchSize {
		end := min(start+accountClosureMongoBatchSize, len(values))
		if _, err := collection.UpdateMany(
			ctx,
			bson.M{field: bson.M{"$in": values[start:end]}},
			bson.M{"$set": set},
		); err != nil {
			return err
		}
	}
	return nil
}

func deleteByStringValues(
	ctx context.Context,
	collection *mongo.Collection,
	field string,
	values []string,
) error {
	for start := 0; start < len(values); start += accountClosureMongoBatchSize {
		end := min(start+accountClosureMongoBatchSize, len(values))
		if _, err := collection.DeleteMany(
			ctx,
			bson.M{field: bson.M{"$in": values[start:end]}},
		); err != nil {
			return err
		}
	}
	return nil
}
