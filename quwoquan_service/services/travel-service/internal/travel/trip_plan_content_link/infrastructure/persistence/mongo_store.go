package persistence

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/domain/ports"
)

const (
	linkCollection     = "trip_plan_content_links"
	receiptCollection  = "trip_plan_content_link_command_receipts"
	outboxCollection   = "trip_plan_content_link_outbox"
	sequenceCollection = "trip_plan_content_link_outbox_sequences"
)

type MongoStore struct {
	links     *mongo.Collection
	receipts  *mongo.Collection
	outbox    *mongo.Collection
	sequences *mongo.Collection
}

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		panic("TripPlanContentLink MongoStore requires database")
	}
	return &MongoStore{
		links: database.Collection(linkCollection), receipts: database.Collection(receiptCollection),
		outbox: database.Collection(outboxCollection), sequences: database.Collection(sequenceCollection),
	}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.links.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "tripId", Value: 1}, {Key: "postId", Value: 1}},
			Options: options.Index().SetName("uq_trip_plan_content_link_post").SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "tripId", Value: 1}, {Key: "status", Value: 1},
				{Key: "dayIndex", Value: 1}, {Key: "itemId", Value: 1}, {Key: "updatedAt", Value: -1},
			},
			Options: options.Index().SetName("idx_trip_plan_content_link_timeline"),
		},
	}); err != nil {
		return err
	}
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "expiresAt", Value: 1}},
		Options: options.Index().SetName("ttl_trip_plan_content_link_command_receipts").SetExpireAfterSeconds(0),
	}); err != nil {
		return err
	}
	_, err := store.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "publishedAt", Value: 1}, {Key: "leaseExpiresAt", Value: 1}, {Key: "outboxSequence", Value: 1}},
			Options: options.Index().SetName("idx_trip_plan_content_link_outbox_pending"),
		},
		{
			Keys:    bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}},
			Options: options.Index().SetName("uq_trip_plan_content_link_outbox_version").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "outboxSequence", Value: 1}},
			Options: options.Index().SetName("uq_trip_plan_content_link_outbox_sequence").SetUnique(true),
		},
	})
	return err
}

func (store *MongoStore) Get(ctx context.Context, tripID, postID string) (model.Link, error) {
	var link model.Link
	err := store.links.FindOne(ctx, linkFilter(tripID, postID)).Decode(&link)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Link{}, ports.ErrNotFound
	}
	return link, err
}

func (store *MongoStore) ListActive(ctx context.Context, tripID string) ([]model.Link, error) {
	cursor, err := store.links.Find(
		ctx,
		bson.M{"tripId": strings.TrimSpace(tripID), "status": model.StatusActive},
		options.Find().SetSort(bson.D{
			{Key: "dayIndex", Value: 1}, {Key: "updatedAt", Value: -1}, {Key: "_id", Value: 1},
		}),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var links []model.Link
	if err := cursor.All(ctx, &links); err != nil {
		return nil, err
	}
	if links == nil {
		links = []model.Link{}
	}
	return links, nil
}

type receiptDocument struct {
	ID            string     `bson:"_id"`
	CommandDigest string     `bson:"commandDigest"`
	Link          model.Link `bson:"link"`
	ExpiresAt     time.Time  `bson:"expiresAt"`
}

func (document receiptDocument) receipt() ports.Receipt {
	return ports.Receipt{
		IdempotencyKey: document.ID, CommandDigest: document.CommandDigest,
		Result: ports.CommandResult{Link: document.Link}, ExpiresAt: document.ExpiresAt,
	}
}

func (store *MongoStore) FindReceipt(ctx context.Context, key string) (ports.Receipt, bool, error) {
	var document receiptDocument
	err := store.receipts.FindOne(ctx, bson.M{"_id": strings.TrimSpace(key)}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return ports.Receipt{}, false, nil
	}
	if err != nil {
		return ports.Receipt{}, false, err
	}
	return document.receipt(), true, nil
}

func (store *MongoStore) Commit(ctx context.Context, commit ports.Commit) error {
	if err := validateCommit(commit); err != nil {
		return err
	}
	if receipt, found, err := store.FindReceipt(ctx, commit.Receipt.IdempotencyKey); err != nil {
		return err
	} else if found {
		if receipt.CommandDigest != commit.Receipt.CommandDigest {
			return ports.ErrIdempotencyConflict
		}
		return nil
	}
	session, err := store.links.Database().Client().StartSession()
	if err != nil {
		return err
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if receipt, found, findErr := store.FindReceipt(txCtx, commit.Receipt.IdempotencyKey); findErr != nil {
			return nil, findErr
		} else if found {
			if receipt.CommandDigest != commit.Receipt.CommandDigest {
				return nil, ports.ErrIdempotencyConflict
			}
			return nil, nil
		}
		if err := store.persistLink(txCtx, commit); err != nil {
			return nil, err
		}
		if err := store.appendOutbox(txCtx, commit); err != nil {
			return nil, err
		}
		_, insertErr := store.receipts.InsertOne(txCtx, receiptDocument{
			ID: commit.Receipt.IdempotencyKey, CommandDigest: commit.Receipt.CommandDigest,
			Link: commit.Receipt.Result.Link, ExpiresAt: commit.Receipt.ExpiresAt.UTC(),
		})
		if mongo.IsDuplicateKeyError(insertErr) {
			return nil, ports.ErrIdempotencyConflict
		}
		return nil, insertErr
	})
	return err
}

func (store *MongoStore) persistLink(ctx context.Context, commit ports.Commit) error {
	if commit.ExpectedVersion == 0 {
		if _, err := store.links.InsertOne(ctx, commit.Link); err != nil {
			if mongo.IsDuplicateKeyError(err) {
				return ports.ErrCommitConflict
			}
			return err
		}
		return nil
	}
	result, err := store.links.ReplaceOne(ctx, bson.M{
		"_id": commit.Link.LinkID, "version": commit.ExpectedVersion,
	}, commit.Link)
	if err != nil {
		return err
	}
	if result.MatchedCount != 1 {
		return ports.ErrCommitConflict
	}
	return nil
}

func (store *MongoStore) appendOutbox(ctx context.Context, commit ports.Commit) error {
	var sequence struct {
		Value int64 `bson:"value"`
	}
	if err := store.sequences.FindOneAndUpdate(
		ctx,
		bson.M{"_id": "TripPlanContentLink"},
		bson.M{"$inc": bson.M{"value": int64(1)}},
		options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
	).Decode(&sequence); err != nil {
		return err
	}
	_, err := store.outbox.InsertOne(ctx, bson.M{
		"_id": commit.Event.EventID, "outboxSequence": sequence.Value,
		"eventType": commit.Event.EventType, "aggregateId": commit.Event.AggregateID,
		"aggregateVersion": commit.Event.AggregateVersion, "payloadJson": commit.Event.Payload,
		"occurredAt": commit.Event.OccurredAt.UTC(), "publishAttempts": 0,
	})
	if mongo.IsDuplicateKeyError(err) {
		return ports.ErrCommitConflict
	}
	return err
}

func linkFilter(tripID, postID string) bson.M {
	return bson.M{"tripId": strings.TrimSpace(tripID), "postId": strings.TrimSpace(postID)}
}

func validateCommit(commit ports.Commit) error {
	if commit.Link.Validate() != nil || strings.TrimSpace(commit.Receipt.IdempotencyKey) == "" ||
		strings.TrimSpace(commit.Receipt.CommandDigest) == "" || commit.Receipt.ExpiresAt.IsZero() ||
		strings.TrimSpace(commit.Event.EventID) == "" ||
		commit.Event.EventType != "TripPlanContentLinkChanged" ||
		commit.Event.AggregateID != commit.Link.LinkID ||
		commit.Event.AggregateVersion != commit.Link.Version || commit.Event.OccurredAt.IsZero() {
		return model.ErrInvalidArgument
	}
	return nil
}

var _ ports.Store = (*MongoStore)(nil)
