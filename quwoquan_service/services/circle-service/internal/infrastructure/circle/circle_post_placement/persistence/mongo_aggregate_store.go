package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	placementmodel "quwoquan_service/services/circle-service/internal/domain/circle/circle_post_placement/model"
	placementports "quwoquan_service/services/circle-service/internal/domain/circle/circle_post_placement/ports"
)

const (
	placementCollection  = "circle_post_placements"
	receiptCollection    = "circle_post_placement_command_receipts"
	outboxCollection     = "circle_post_placement_outbox"
	sequenceCollection   = "circle_post_placement_outbox_sequences"
	checkpointCollection = "circle_post_placement_projection_checkpoints"
)

type MongoAggregateStore struct {
	placements  *mongo.Collection
	receipts    *mongo.Collection
	outbox      *mongo.Collection
	sequences   *mongo.Collection
	checkpoints *mongo.Collection
}

var _ placementports.AggregateStore = (*MongoAggregateStore)(nil)

func NewMongoAggregateStore(database *mongo.Database) *MongoAggregateStore {
	if database == nil {
		panic("CirclePostPlacement MongoAggregateStore requires database")
	}
	return &MongoAggregateStore{
		placements:  database.Collection(placementCollection),
		receipts:    database.Collection(receiptCollection),
		outbox:      database.Collection(outboxCollection),
		sequences:   database.Collection(sequenceCollection),
		checkpoints: database.Collection(checkpointCollection),
	}
}

func (store *MongoAggregateStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.placements.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "postId", Value: 1}, {Key: "circleId", Value: 1}, {Key: "groupId", Value: 1}}, Options: options.Index().SetName("idx_circle_post_placement_identity").SetUnique(true)},
		{Keys: bson.D{{Key: "circleId", Value: 1}, {Key: "state", Value: 1}, {Key: "pinned", Value: -1}, {Key: "featured", Value: -1}, {Key: "lastActiveAt", Value: -1}}, Options: options.Index().SetName("idx_circle_post_placement_feed")},
	}); err != nil {
		return err
	}
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "expiresAt", Value: 1}},
		Options: options.Index().SetName("idx_circle_post_placement_receipt_expiry").SetExpireAfterSeconds(0),
	}); err != nil {
		return err
	}
	_, err := store.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}}, Options: options.Index().SetName("idx_circle_post_placement_outbox_version").SetUnique(true)},
		{Keys: bson.D{{Key: "outboxSequence", Value: 1}}, Options: options.Index().SetName("idx_circle_post_placement_outbox_sequence").SetUnique(true)},
	})
	return err
}

func (store *MongoAggregateStore) Load(ctx context.Context, placementID string) (placementmodel.CirclePostPlacement, bool, error) {
	return store.load(ctx, bson.D{{Key: "_id", Value: strings.TrimSpace(placementID)}})
}

func (store *MongoAggregateStore) Commit(ctx context.Context, request placementports.CommitRequest) (placementports.CommitReceipt, error) {
	if err := request.Change.Validate(); err != nil || strings.TrimSpace(request.ReceiptKey) == "" ||
		strings.TrimSpace(request.CommandDigest) == "" || request.ReceiptExpiresAt.IsZero() {
		return placementports.CommitReceipt{}, placementmodel.ErrInvalidChange
	}
	if replay, found, err := store.findReceipt(ctx, request.ReceiptKey, request.CommandDigest); err != nil || found {
		return replay, err
	}
	session, err := store.placements.Database().Client().StartSession()
	if err != nil {
		return placementports.CommitReceipt{}, err
	}
	defer session.EndSession(ctx)

	var committed placementports.CommitReceipt
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if replay, found, findErr := store.findReceipt(txCtx, request.ReceiptKey, request.CommandDigest); findErr != nil {
			return nil, findErr
		} else if found {
			committed = replay
			return nil, nil
		}
		current, found, loadErr := store.loadForChange(txCtx, request.Change)
		if loadErr != nil {
			return nil, loadErr
		}
		var currentPointer *placementmodel.CirclePostPlacement
		if found {
			currentPointer = &current
		}
		next, eventType, applyErr := request.Change.Apply(currentPointer)
		if applyErr != nil {
			return nil, applyErr
		}
		if request.Change.Kind == placementmodel.ChangePlace {
			if _, insertErr := store.placements.InsertOne(txCtx, placementDocumentFrom(next)); insertErr != nil {
				if mongo.IsDuplicateKeyError(insertErr) {
					return nil, placementmodel.ErrAlreadyExists
				}
				return nil, insertErr
			}
		} else {
			result, replaceErr := store.placements.ReplaceOne(txCtx, bson.D{
				{Key: "_id", Value: next.ID}, {Key: "circleId", Value: next.CircleID},
				{Key: "version", Value: request.Change.ExpectedVersion},
			}, placementDocumentFrom(next))
			if replaceErr != nil {
				return nil, replaceErr
			}
			if result.MatchedCount != 1 {
				return nil, placementmodel.ErrVersionConflict
			}
		}
		var sequenceCounter struct {
			Value int64 `bson:"value"`
		}
		if sequenceErr := store.sequences.FindOneAndUpdate(
			txCtx,
			bson.M{"_id": "CirclePostPlacement"},
			bson.M{"$inc": bson.M{"value": int64(1)}},
			options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
		).Decode(&sequenceCounter); sequenceErr != nil {
			return nil, sequenceErr
		}
		payloadJSON, marshalErr := json.Marshal(placementEventPayload(next))
		if marshalErr != nil {
			return nil, marshalErr
		}
		eventID := next.ID + ":" + string(eventType) + ":" + strconv.FormatInt(next.Version, 10)
		if _, insertErr := store.outbox.InsertOne(txCtx, bson.D{
			{Key: "_id", Value: eventID}, {Key: "eventType", Value: eventType},
			{Key: "aggregateId", Value: next.ID}, {Key: "aggregateVersion", Value: next.Version},
			{Key: "outboxSequence", Value: sequenceCounter.Value},
			{Key: "payloadJson", Value: string(payloadJSON)},
			{Key: "occurredAt", Value: next.UpdatedAt.UTC()},
		}); insertErr != nil {
			return nil, insertErr
		}
		committed = placementports.CommitReceipt{
			PlacementID: next.ID, Version: next.Version, State: next.State,
		}
		_, insertErr := store.receipts.InsertOne(txCtx, bson.D{
			{Key: "_id", Value: request.ReceiptKey}, {Key: "commandDigest", Value: request.CommandDigest},
			{Key: "placementId", Value: committed.PlacementID}, {Key: "version", Value: committed.Version},
			{Key: "state", Value: committed.State}, {Key: "expiresAt", Value: request.ReceiptExpiresAt.UTC()},
		})
		return nil, insertErr
	})
	if err != nil {
		// UnknownTransactionCommitResult and concurrent identical commands are
		// resolved exclusively through the durable receipt.
		if replay, found, replayErr := store.findReceipt(ctx, request.ReceiptKey, request.CommandDigest); replayErr == nil && found {
			return replay, nil
		}
		return placementports.CommitReceipt{}, err
	}
	return committed, nil
}

func (store *MongoAggregateStore) loadForChange(ctx context.Context, change placementmodel.ChangeSet) (placementmodel.CirclePostPlacement, bool, error) {
	if change.Kind == placementmodel.ChangePlace {
		return store.load(ctx, bson.D{
			{Key: "postId", Value: change.PostID}, {Key: "circleId", Value: change.CircleID},
			{Key: "groupId", Value: change.GroupID},
		})
	}
	return store.load(ctx, bson.D{{Key: "_id", Value: change.PlacementID}})
}

func (store *MongoAggregateStore) load(ctx context.Context, filter any) (placementmodel.CirclePostPlacement, bool, error) {
	var document placementDocument
	err := store.placements.FindOne(ctx, filter).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return placementmodel.CirclePostPlacement{}, false, nil
	}
	if err != nil {
		return placementmodel.CirclePostPlacement{}, false, err
	}
	return document.toModel(), true, nil
}

// RecordNoopReceipt 落"目标状态已满足"回执：不递增 version、不写 outbox。
func (store *MongoAggregateStore) RecordNoopReceipt(ctx context.Context, noop placementports.NoopReceipt) (placementports.CommitReceipt, error) {
	if strings.TrimSpace(noop.PlacementID) == "" ||
		strings.TrimSpace(noop.ReceiptKey) == "" ||
		strings.TrimSpace(noop.CommandDigest) == "" {
		return placementports.CommitReceipt{}, placementmodel.ErrInvalidChange
	}
	if replay, found, err := store.findReceipt(ctx, noop.ReceiptKey, noop.CommandDigest); err != nil || found {
		return replay, err
	}
	expiresAt := noop.ReceiptExpiresAt.UTC()
	if expiresAt.IsZero() {
		expiresAt = time.Now().UTC().Add(24 * time.Hour)
	}
	_, err := store.receipts.InsertOne(ctx, bson.D{
		{Key: "_id", Value: noop.ReceiptKey}, {Key: "commandDigest", Value: noop.CommandDigest},
		{Key: "placementId", Value: noop.PlacementID}, {Key: "version", Value: noop.Version},
		{Key: "state", Value: noop.State}, {Key: "expiresAt", Value: expiresAt},
	})
	if err != nil {
		if mongo.IsDuplicateKeyError(err) {
			if replay, found, replayErr := store.findReceipt(ctx, noop.ReceiptKey, noop.CommandDigest); replayErr == nil && found {
				return replay, nil
			}
		}
		return placementports.CommitReceipt{}, err
	}
	return placementports.CommitReceipt{
		PlacementID: noop.PlacementID, Version: noop.Version, State: noop.State,
	}, nil
}

func (store *MongoAggregateStore) findReceipt(ctx context.Context, receiptKey, commandDigest string) (placementports.CommitReceipt, bool, error) {
	var document struct {
		CommandDigest string                                  `bson:"commandDigest"`
		PlacementID   string                                  `bson:"placementId"`
		Version       int64                                   `bson:"version"`
		State         placementmodel.CirclePostPlacementState `bson:"state"`
	}
	err := store.receipts.FindOne(ctx, bson.D{{Key: "_id", Value: receiptKey}}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return placementports.CommitReceipt{}, false, nil
	}
	if err != nil {
		return placementports.CommitReceipt{}, false, err
	}
	if document.CommandDigest != commandDigest {
		return placementports.CommitReceipt{}, false, placementmodel.ErrIdempotencyConflict
	}
	return placementports.CommitReceipt{
		PlacementID: document.PlacementID, Version: document.Version,
		State: document.State, Replayed: true,
	}, true, nil
}

type placementDocument struct {
	ID             string                                  `bson:"_id"`
	Version        int64                                   `bson:"version"`
	PostID         string                                  `bson:"postId"`
	OwnerPersonaID string                                  `bson:"ownerPersonaId"`
	CircleID       string                                  `bson:"circleId"`
	GroupID        string                                  `bson:"groupId"`
	State          placementmodel.CirclePostPlacementState `bson:"state"`
	Pinned         bool                                    `bson:"pinned"`
	PinnedAt       *bson.DateTime                          `bson:"pinnedAt,omitempty"`
	Featured       bool                                    `bson:"featured"`
	FeaturedAt     *bson.DateTime                          `bson:"featuredAt,omitempty"`
	LastActiveAt   bson.DateTime                           `bson:"lastActiveAt"`
	CreatedAt      bson.DateTime                           `bson:"createdAt"`
	UpdatedAt      bson.DateTime                           `bson:"updatedAt"`
}

func placementDocumentFrom(value placementmodel.CirclePostPlacement) placementDocument {
	result := placementDocument{
		ID: value.ID, Version: value.Version, PostID: value.PostID,
		OwnerPersonaID: value.OwnerPersonaID, CircleID: value.CircleID, GroupID: value.GroupID,
		State: value.State, Pinned: value.Pinned, Featured: value.Featured,
		LastActiveAt: bson.NewDateTimeFromTime(value.LastActiveAt.UTC()),
		CreatedAt:    bson.NewDateTimeFromTime(value.CreatedAt.UTC()),
		UpdatedAt:    bson.NewDateTimeFromTime(value.UpdatedAt.UTC()),
	}
	if !value.PinnedAt.IsZero() {
		date := bson.NewDateTimeFromTime(value.PinnedAt.UTC())
		result.PinnedAt = &date
	}
	if !value.FeaturedAt.IsZero() {
		date := bson.NewDateTimeFromTime(value.FeaturedAt.UTC())
		result.FeaturedAt = &date
	}
	return result
}

func (document placementDocument) toModel() placementmodel.CirclePostPlacement {
	value := placementmodel.CirclePostPlacement{
		ID: document.ID, Version: document.Version, PostID: document.PostID,
		OwnerPersonaID: document.OwnerPersonaID, CircleID: document.CircleID, GroupID: document.GroupID,
		State: document.State, Pinned: document.Pinned, Featured: document.Featured,
		LastActiveAt: document.LastActiveAt.Time().UTC(), CreatedAt: document.CreatedAt.Time().UTC(),
		UpdatedAt: document.UpdatedAt.Time().UTC(),
	}
	if document.PinnedAt != nil {
		value.PinnedAt = document.PinnedAt.Time().UTC()
	}
	if document.FeaturedAt != nil {
		value.FeaturedAt = document.FeaturedAt.Time().UTC()
	}
	return value
}

func placementEventPayload(value placementmodel.CirclePostPlacement) bson.M {
	payload := bson.M{
		"_id": value.ID, "version": value.Version, "postId": value.PostID,
		"ownerPersonaId": value.OwnerPersonaID, "circleId": value.CircleID,
		"groupId": value.GroupID, "state": value.State, "pinned": value.Pinned,
		"featured": value.Featured, "lastActiveAt": value.LastActiveAt.UTC(),
		"createdAt": value.CreatedAt.UTC(), "updatedAt": value.UpdatedAt.UTC(),
	}
	if !value.PinnedAt.IsZero() {
		payload["pinnedAt"] = value.PinnedAt.UTC()
	}
	if !value.FeaturedAt.IsZero() {
		payload["featuredAt"] = value.FeaturedAt.UTC()
	}
	return payload
}
