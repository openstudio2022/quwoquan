package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	learningapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
)

const learningFactSequenceID = "assistant_learning_fact"

type MongoStore struct {
	facts     *mongo.Collection
	receipts  *mongo.Collection
	outbox    *mongo.Collection
	sequences *mongo.Collection
}

type receiptDocument struct {
	ID            string `bson:"_id"`
	model.Receipt `bson:",inline"`
}

type outboxDocument struct {
	ID             string                `bson:"_id"`
	EventType      string                `bson:"eventType"`
	AppendSequence int64                 `bson:"appendSequence"`
	Payload        model.RedactedPayload `bson:"payload"`
	OccurredAt     time.Time             `bson:"occurredAt"`
	ClaimOwner     string                `bson:"claimOwner,omitempty"`
	ClaimUntil     *time.Time            `bson:"claimUntil,omitempty"`
	PublishedAt    *time.Time            `bson:"publishedAt,omitempty"`
	PublishedRef   string                `bson:"publishedRef,omitempty"`
}

type PendingOutboxEvent struct {
	ID             string
	EventType      string
	AppendSequence int64
	Payload        model.RedactedPayload
	OccurredAt     time.Time
}

var ErrOutboxClaimLost = errors.New("assistant learning fact outbox claim lost")

type sequenceDocument struct {
	ID    string `bson:"_id"`
	Value int64  `bson:"value"`
}

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		return &MongoStore{}
	}
	return &MongoStore{
		facts:     database.Collection("assistant_learning_facts"),
		receipts:  database.Collection("assistant_learning_fact_receipts"),
		outbox:    database.Collection("assistant_learning_fact_outbox"),
		sequences: database.Collection("assistant_learning_fact_sequences"),
	}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	if !store.ready() {
		return learningapplication.ErrStoreUnavailable
	}
	if _, err := store.facts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{{Key: "appendSequence", Value: 1}},
			Options: options.Index().
				SetName("uq_assistant_learning_fact_sequence").
				SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "userId", Value: 1},
				{Key: "appendSequence", Value: 1},
			},
			Options: options.Index().
				SetName("idx_assistant_learning_fact_owner_sequence"),
		},
	}); err != nil {
		return unavailable("ensure fact indexes", err)
	}
	if _, err := store.outbox.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "publishedAt", Value: 1},
			{Key: "appendSequence", Value: 1},
		},
		Options: options.Index().
			SetName("idx_assistant_learning_fact_outbox_pending"),
	}); err != nil {
		return unavailable("ensure outbox indexes", err)
	}
	if _, err := store.outbox.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "publishedAt", Value: 1},
			{Key: "claimUntil", Value: 1},
			{Key: "appendSequence", Value: 1},
		},
		Options: options.Index().
			SetName("idx_assistant_learning_fact_outbox_claimable"),
	}); err != nil {
		return unavailable("ensure claimable outbox index", err)
	}
	return nil
}

func (store *MongoStore) Append(
	ctx context.Context,
	fact model.Fact,
) (model.Receipt, error) {
	if !store.ready() {
		return model.Receipt{}, learningapplication.ErrStoreUnavailable
	}
	session, err := store.facts.Database().Client().StartSession()
	if err != nil {
		return model.Receipt{}, unavailable("start append transaction", err)
	}
	defer session.EndSession(ctx)

	var result model.Receipt
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		existing, found, loadErr := store.loadReceipt(txCtx, fact.StorageID)
		if loadErr != nil {
			return nil, loadErr
		}
		if found {
			if existing.PayloadDigest != fact.PayloadDigest {
				return nil, learningapplication.ErrIdentityConflict
			}
			existing.Deduplicated = true
			result = existing
			return nil, nil
		}

		sequence, sequenceErr := store.nextSequence(txCtx)
		if sequenceErr != nil {
			return nil, sequenceErr
		}
		fact.AppendSequence = sequence
		if _, insertErr := store.facts.InsertOne(txCtx, fact); insertErr != nil {
			return nil, insertErr
		}
		result = model.Receipt{
			EventID:        fact.EventID,
			Accepted:       true,
			AppendSequence: sequence,
			PayloadDigest:  fact.PayloadDigest,
			RecordedAt:     fact.RecordedAt,
		}
		if _, receiptErr := store.receipts.InsertOne(
			txCtx,
			receiptDocument{ID: fact.StorageID, Receipt: result},
		); receiptErr != nil {
			return nil, receiptErr
		}
		if _, outboxErr := store.outbox.InsertOne(txCtx, outboxDocument{
			ID:             fact.StorageID,
			EventType:      "AssistantLearningFactAppended",
			AppendSequence: sequence,
			Payload:        fact.RedactedPayload(),
			OccurredAt:     fact.OccurredAt,
		}); outboxErr != nil {
			return nil, outboxErr
		}
		return nil, nil
	})
	if err == nil {
		return result, nil
	}
	if errors.Is(err, learningapplication.ErrIdentityConflict) {
		return model.Receipt{}, err
	}
	if mongo.IsDuplicateKeyError(err) {
		existing, found, loadErr := store.loadReceipt(ctx, fact.StorageID)
		if loadErr == nil && found {
			if existing.PayloadDigest != fact.PayloadDigest {
				return model.Receipt{}, learningapplication.ErrIdentityConflict
			}
			existing.Deduplicated = true
			return existing, nil
		}
	}
	return model.Receipt{}, unavailable("append transaction", err)
}

func (store *MongoStore) ClaimPendingOutbox(
	ctx context.Context,
	ownerID string,
	lease time.Duration,
	limit int,
) ([]PendingOutboxEvent, error) {
	if !store.ready() {
		return nil, learningapplication.ErrStoreUnavailable
	}
	ownerID = strings.TrimSpace(ownerID)
	if ownerID == "" || lease <= 0 {
		return nil, unavailable(
			"claim pending outbox",
			errors.New("owner and positive lease are required"),
		)
	}
	if limit <= 0 || limit > 512 {
		limit = 128
	}
	events := make([]PendingOutboxEvent, 0, limit)
	for len(events) < limit {
		now := time.Now().UTC()
		var document outboxDocument
		err := store.outbox.FindOneAndUpdate(
			ctx,
			bson.M{
				"publishedAt": bson.M{"$exists": false},
				"$or": bson.A{
					bson.M{"claimUntil": bson.M{"$exists": false}},
					bson.M{"claimUntil": bson.M{"$lte": now}},
				},
			},
			bson.M{"$set": bson.M{
				"claimOwner": ownerID,
				"claimUntil": now.Add(lease),
			}},
			options.FindOneAndUpdate().
				SetSort(bson.D{{Key: "appendSequence", Value: 1}}).
				SetReturnDocument(options.After),
		).Decode(&document)
		if errors.Is(err, mongo.ErrNoDocuments) {
			break
		}
		if err != nil {
			return nil, unavailable("claim pending outbox", err)
		}
		events = append(events, PendingOutboxEvent{
			ID:             document.ID,
			EventType:      document.EventType,
			AppendSequence: document.AppendSequence,
			Payload:        document.Payload,
			OccurredAt:     document.OccurredAt,
		})
	}
	return events, nil
}

func (store *MongoStore) ReleaseOutboxClaim(
	ctx context.Context,
	eventID string,
	ownerID string,
) error {
	if !store.ready() {
		return learningapplication.ErrStoreUnavailable
	}
	_, err := store.outbox.UpdateOne(
		ctx,
		bson.M{
			"_id":        strings.TrimSpace(eventID),
			"claimOwner": strings.TrimSpace(ownerID),
			"publishedAt": bson.M{
				"$exists": false,
			},
		},
		bson.M{"$unset": bson.M{
			"claimOwner": "",
			"claimUntil": "",
		}},
	)
	if err != nil {
		return unavailable("release outbox claim", err)
	}
	return nil
}

func (store *MongoStore) MarkOutboxPublished(
	ctx context.Context,
	eventID string,
	ownerID string,
	publishedRef string,
	publishedAt time.Time,
) error {
	if !store.ready() {
		return learningapplication.ErrStoreUnavailable
	}
	result, err := store.outbox.UpdateOne(
		ctx,
		bson.M{
			"_id":         strings.TrimSpace(eventID),
			"claimOwner":  strings.TrimSpace(ownerID),
			"publishedAt": bson.M{"$exists": false},
		},
		bson.M{"$set": bson.M{
			"publishedAt":  publishedAt.UTC(),
			"publishedRef": strings.TrimSpace(publishedRef),
		}, "$unset": bson.M{
			"claimOwner": "",
			"claimUntil": "",
		}},
	)
	if err != nil {
		return unavailable("mark outbox published", err)
	}
	if result.MatchedCount == 0 {
		var existing outboxDocument
		loadErr := store.outbox.FindOne(
			ctx,
			bson.M{"_id": strings.TrimSpace(eventID)},
		).Decode(&existing)
		if loadErr == nil && existing.PublishedAt != nil {
			return nil
		}
		return ErrOutboxClaimLost
	}
	return nil
}

func (store *MongoStore) loadReceipt(
	ctx context.Context,
	identity string,
) (model.Receipt, bool, error) {
	var document receiptDocument
	err := store.receipts.FindOne(ctx, bson.M{"_id": identity}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Receipt{}, false, nil
	}
	if err != nil {
		return model.Receipt{}, false, err
	}
	return document.Receipt, true, nil
}

func (store *MongoStore) nextSequence(ctx context.Context) (int64, error) {
	var sequence sequenceDocument
	err := store.sequences.FindOneAndUpdate(
		ctx,
		bson.M{"_id": learningFactSequenceID},
		bson.M{"$inc": bson.M{"value": int64(1)}},
		options.FindOneAndUpdate().
			SetUpsert(true).
			SetReturnDocument(options.After),
	).Decode(&sequence)
	if err != nil {
		return 0, err
	}
	return sequence.Value, nil
}

func (store *MongoStore) ready() bool {
	return store != nil &&
		store.facts != nil &&
		store.receipts != nil &&
		store.outbox != nil &&
		store.sequences != nil
}

func unavailable(stage string, err error) error {
	return fmt.Errorf(
		"%w: %s: %v",
		learningapplication.ErrStoreUnavailable,
		stage,
		err,
	)
}
