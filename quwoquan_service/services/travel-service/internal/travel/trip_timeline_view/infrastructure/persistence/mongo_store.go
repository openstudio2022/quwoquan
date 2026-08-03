package persistence

import (
	"context"
	"errors"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	mapmodel "quwoquan_service/services/travel-service/internal/travel/trip_map_view/domain/model"
	mapports "quwoquan_service/services/travel-service/internal/travel/trip_map_view/domain/ports"
	timelinemodel "quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/domain/ports"
)

const (
	timelineCollection = "trip_timeline_views"
	mapCollection      = "trip_map_views"
	receiptCollection  = "trip_timeline_projection_receipts"
)

type MongoStore struct {
	timelines *mongo.Collection
	maps      *mongo.Collection
	receipts  *mongo.Collection
}

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		panic("TripTimelineView MongoStore requires database")
	}
	return &MongoStore{
		timelines: database.Collection(timelineCollection),
		maps:      database.Collection(mapCollection),
		receipts:  database.Collection(receiptCollection),
	}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.timelines.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "currentRevisionId", Value: 1}, {Key: "currentRevisionNumber", Value: 1}},
		Options: options.Index().SetName("idx_trip_timeline_source_revision"),
	}); err != nil {
		return err
	}
	if _, err := store.maps.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "currentRevisionId", Value: 1}, {Key: "currentRevisionNumber", Value: 1}},
		Options: options.Index().SetName("idx_trip_map_source_revision"),
	}); err != nil {
		return err
	}
	_, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "tripId", Value: 1}, {Key: "appliedAt", Value: -1}},
		Options: options.Index().SetName("idx_trip_projection_receipt_trip"),
	})
	return err
}

func (store *MongoStore) GetTimeline(ctx context.Context, tripID string) (timelinemodel.View, error) {
	var view timelinemodel.View
	err := store.timelines.FindOne(ctx, bson.M{"_id": strings.TrimSpace(tripID)}).Decode(&view)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return timelinemodel.View{}, ports.ErrNotFound
	}
	return view, err
}

func (store *MongoStore) GetMap(ctx context.Context, tripID string) (mapmodel.View, error) {
	var view mapmodel.View
	err := store.maps.FindOne(ctx, bson.M{"_id": strings.TrimSpace(tripID)}).Decode(&view)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return mapmodel.View{}, mapports.ErrNotFound
	}
	return view, err
}

func (store *MongoStore) FindReceipt(
	ctx context.Context,
	sourceEventID string,
) (ports.ProjectionReceipt, bool, error) {
	var receipt ports.ProjectionReceipt
	err := store.receipts.FindOne(ctx, bson.M{"_id": strings.TrimSpace(sourceEventID)}).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return ports.ProjectionReceipt{}, false, nil
	}
	if err != nil {
		return ports.ProjectionReceipt{}, false, err
	}
	return receipt, true, nil
}

func (store *MongoStore) CommitProjection(ctx context.Context, commit ports.ProjectionCommit) error {
	if err := validateCommit(commit); err != nil {
		return err
	}
	if receipt, found, err := store.FindReceipt(ctx, commit.Receipt.SourceEventID); err != nil {
		return err
	} else if found {
		return validateExistingReceipt(receipt, commit.Receipt)
	}
	session, err := store.timelines.Database().Client().StartSession()
	if err != nil {
		return err
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if receipt, found, findErr := store.FindReceipt(txCtx, commit.Receipt.SourceEventID); findErr != nil {
			return nil, findErr
		} else if found {
			return nil, validateExistingReceipt(receipt, commit.Receipt)
		}
		if _, replaceErr := store.timelines.ReplaceOne(
			txCtx,
			bson.M{"_id": commit.Timeline.TripID},
			commit.Timeline,
			options.Replace().SetUpsert(true),
		); replaceErr != nil {
			return nil, replaceErr
		}
		if _, replaceErr := store.maps.ReplaceOne(
			txCtx,
			bson.M{"_id": commit.Map.TripID},
			commit.Map,
			options.Replace().SetUpsert(true),
		); replaceErr != nil {
			return nil, replaceErr
		}
		_, insertErr := store.receipts.InsertOne(txCtx, commit.Receipt)
		if mongo.IsDuplicateKeyError(insertErr) {
			return nil, ports.ErrReceiptConflict
		}
		return nil, insertErr
	})
	if !errors.Is(err, ports.ErrReceiptConflict) {
		return err
	}
	receipt, found, findErr := store.FindReceipt(ctx, commit.Receipt.SourceEventID)
	if findErr != nil || !found {
		return err
	}
	return validateExistingReceipt(receipt, commit.Receipt)
}

func validateExistingReceipt(current, expected ports.ProjectionReceipt) error {
	if current.TripID != expected.TripID || current.SourceDigest != expected.SourceDigest {
		return ports.ErrReceiptConflict
	}
	return nil
}

func validateCommit(commit ports.ProjectionCommit) error {
	if commit.Timeline.Validate() != nil || commit.Map.Validate() != nil ||
		commit.Timeline.TripID != commit.Map.TripID ||
		commit.Timeline.SourceDigest != commit.Map.SourceDigest ||
		commit.Timeline.SourceEventID != commit.Map.SourceEventID ||
		strings.TrimSpace(commit.Receipt.SourceEventID) == "" ||
		commit.Receipt.SourceEventID != commit.Timeline.SourceEventID ||
		commit.Receipt.TripID != commit.Timeline.TripID ||
		commit.Receipt.SourceDigest != commit.Timeline.SourceDigest ||
		commit.Receipt.AppliedAt.IsZero() {
		return timelinemodel.ErrInvalidView
	}
	return nil
}

var (
	_ ports.Store    = (*MongoStore)(nil)
	_ mapports.Store = (*MongoStore)(nil)
)
