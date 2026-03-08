package persistence

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	model "quwoquan_service/services/circle-service/internal/domain/circle/model"
)

// MongoFileStore implements FileStore backed by MongoDB.
type MongoFileStore struct {
	coll *mongo.Collection
}

func NewMongoFileStore(coll *mongo.Collection) *MongoFileStore {
	return &MongoFileStore{coll: coll}
}

func (s *MongoFileStore) Create(ctx context.Context, file *model.CircleFile) error {
	_, err := s.coll.InsertOne(ctx, file)
	return err
}

func (s *MongoFileStore) FindByID(ctx context.Context, circleID, fileID string) (*model.CircleFile, bool) {
	var f model.CircleFile
	err := s.coll.FindOne(ctx, bson.M{"_id": fileID, "circleId": circleID}).Decode(&f)
	if err != nil {
		return nil, false
	}
	return &f, true
}

func (s *MongoFileStore) Update(ctx context.Context, circleID, fileID string, file *model.CircleFile) bool {
	file.UpdatedAt = time.Now()
	result, err := s.coll.ReplaceOne(ctx, bson.M{"_id": fileID, "circleId": circleID}, file)
	if err != nil {
		return false
	}
	return result.MatchedCount > 0
}

func (s *MongoFileStore) Delete(ctx context.Context, circleID, fileID string) bool {
	result, err := s.coll.DeleteOne(ctx, bson.M{"_id": fileID, "circleId": circleID})
	if err != nil {
		return false
	}
	return result.DeletedCount > 0
}

func (s *MongoFileStore) ListByCircle(ctx context.Context, circleID string, opts ListFilesOpts) ([]model.CircleFile, string) {
	if opts.Limit <= 0 {
		opts.Limit = 20
	}

	filter := bson.M{
		"circleId": circleID,
		"status":   string(model.CircleFileStatusActive),
	}
	if opts.ParentID != "" {
		filter["parentFolderId"] = opts.ParentID
	}
	if opts.Cursor != "" {
		var cursorDoc model.CircleFile
		if err := s.coll.FindOne(ctx, bson.M{"_id": opts.Cursor, "circleId": circleID}).Decode(&cursorDoc); err == nil {
			filter["createdAt"] = bson.M{"$lt": cursorDoc.CreatedAt}
		}
	}

	sortField := bson.D{{Key: "createdAt", Value: -1}}
	if opts.Sort == "name" {
		sortField = bson.D{{Key: "name", Value: 1}}
	} else if opts.Sort == "size" {
		sortField = bson.D{{Key: "sizeBytes", Value: -1}}
	}

	findOpts := options.Find().SetSort(sortField).SetLimit(int64(opts.Limit))
	cur, err := s.coll.Find(ctx, filter, findOpts)
	if err != nil {
		return nil, ""
	}
	defer cur.Close(ctx)

	var files []model.CircleFile
	if err := cur.All(ctx, &files); err != nil {
		return nil, ""
	}

	var nextCursor string
	if len(files) == opts.Limit {
		nextCursor = files[len(files)-1].ID
	}
	return files, nextCursor
}
