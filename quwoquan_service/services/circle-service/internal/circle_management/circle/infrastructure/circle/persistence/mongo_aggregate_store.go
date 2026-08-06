// Package persistence 实现 Circle 聚合本体的事务化 AggregateStore：
// state/version、命令回执与 outbox 事实在同一 Mongo 事务提交。
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

	circlemodel "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/model"
	circleports "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/ports"
)

const (
	circleCollection           = "circles"
	circleReceiptCollection    = "circle_command_receipts"
	circleOutboxCollection     = "circle_outbox"
	circleSequenceCollection   = "circle_outbox_sequences"
	circleCheckpointCollection = "circle_projection_checkpoints"
)

type MongoAggregateStore struct {
	circles     *mongo.Collection
	receipts    *mongo.Collection
	outbox      *mongo.Collection
	sequences   *mongo.Collection
	checkpoints *mongo.Collection
}

func NewMongoAggregateStore(database *mongo.Database) *MongoAggregateStore {
	if database == nil {
		panic("Circle MongoAggregateStore requires database")
	}
	return &MongoAggregateStore{
		circles:  database.Collection(circleCollection),
		receipts: database.Collection(circleReceiptCollection),
		outbox:   database.Collection(circleOutboxCollection),
		sequences: database.Collection(
			circleSequenceCollection,
		),
		checkpoints: database.Collection(circleCheckpointCollection),
	}
}

func (store *MongoAggregateStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "expiresAt", Value: 1}},
		Options: options.Index().SetName("idx_circle_receipt_expiry").SetExpireAfterSeconds(0),
	}); err != nil {
		return err
	}
	_, err := store.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}}, Options: options.Index().SetName("idx_circle_outbox_version").SetUnique(true)},
		{Keys: bson.D{{Key: "outboxSequence", Value: 1}}, Options: options.Index().SetName("idx_circle_outbox_sequence").SetUnique(true)},
	})
	return err
}

func (store *MongoAggregateStore) Load(ctx context.Context, circleID string) (circlemodel.Circle, bool, error) {
	var value circlemodel.Circle
	err := store.circles.FindOne(ctx, bson.M{"_id": strings.TrimSpace(circleID)}).Decode(&value)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return circlemodel.Circle{}, false, nil
	}
	if err != nil {
		return circlemodel.Circle{}, false, err
	}
	return value, true, nil
}

func (store *MongoAggregateStore) Commit(ctx context.Context, request circleports.CommitRequest) (circleports.CommitReceipt, error) {
	if strings.TrimSpace(request.Change.CircleID) == "" ||
		strings.TrimSpace(request.ReceiptKey) == "" ||
		strings.TrimSpace(request.CommandDigest) == "" ||
		request.ReceiptExpiresAt.IsZero() {
		return circleports.CommitReceipt{}, circlemodel.ErrInvalidChange
	}
	if replay, found, err := store.findReceipt(ctx, request.ReceiptKey, request.CommandDigest); err != nil || found {
		return replay, err
	}
	session, err := store.circles.Database().Client().StartSession()
	if err != nil {
		return circleports.CommitReceipt{}, err
	}
	defer session.EndSession(ctx)
	var committed circleports.CommitReceipt
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if replay, found, findErr := store.findReceipt(txCtx, request.ReceiptKey, request.CommandDigest); findErr != nil {
			return nil, findErr
		} else if found {
			committed = replay
			return nil, nil
		}
		current, found, loadErr := store.Load(txCtx, request.Change.CircleID)
		if loadErr != nil {
			return nil, loadErr
		}
		var currentPointer *circlemodel.Circle
		if found {
			currentPointer = &current
		}
		next, applyErr := circlemodel.Apply(currentPointer, request.Change)
		if applyErr != nil {
			return nil, applyErr
		}
		if !found {
			if _, insertErr := store.circles.InsertOne(txCtx, next); insertErr != nil {
				if mongo.IsDuplicateKeyError(insertErr) {
					return nil, circlemodel.ErrVersionConflict
				}
				return nil, insertErr
			}
		} else {
			result, replaceErr := store.circles.ReplaceOne(txCtx,
				bson.M{"_id": next.ID, "version": request.Change.ExpectedVersion}, next)
			if replaceErr != nil {
				return nil, replaceErr
			}
			if result.MatchedCount != 1 {
				return nil, circlemodel.ErrVersionConflict
			}
		}
		var sequence struct {
			Value int64 `bson:"value"`
		}
		if sequenceErr := store.sequences.FindOneAndUpdate(txCtx,
			bson.M{"_id": "Circle"}, bson.M{"$inc": bson.M{"value": int64(1)}},
			options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After)).Decode(&sequence); sequenceErr != nil {
			return nil, sequenceErr
		}
		eventType := circleEventType(request.Change.Kind)
		payloadJSON, marshalErr := json.Marshal(circleEventPayloadFor(eventType, next))
		if marshalErr != nil {
			return nil, marshalErr
		}
		eventID := next.ID + ":" + eventType + ":" + strconv.FormatInt(next.Version, 10)
		if _, insertErr := store.outbox.InsertOne(txCtx, bson.M{
			"_id": eventID, "outboxSequence": sequence.Value, "eventType": eventType,
			"aggregateId": next.ID, "aggregateVersion": next.Version,
			"payloadJson": string(payloadJSON), "occurredAt": next.UpdatedAt.UTC(),
		}); insertErr != nil {
			return nil, insertErr
		}
		committed = circleports.CommitReceipt{CircleID: next.ID, Version: next.Version, Status: next.Status}
		_, insertErr := store.receipts.InsertOne(txCtx, bson.M{
			"_id": request.ReceiptKey, "commandDigest": request.CommandDigest,
			"circleId": next.ID, "version": next.Version, "status": next.Status,
			"expiresAt": request.ReceiptExpiresAt.UTC(),
		})
		return nil, insertErr
	})
	if err != nil {
		if replay, found, replayErr := store.findReceipt(ctx, request.ReceiptKey, request.CommandDigest); replayErr == nil && found {
			return replay, nil
		}
		return circleports.CommitReceipt{}, err
	}
	return committed, nil
}

// RecordNoopReceipt 落"目标状态已满足"回执：不递增 version、不写 outbox。
func (store *MongoAggregateStore) RecordNoopReceipt(ctx context.Context, noop circleports.NoopReceipt) (circleports.CommitReceipt, error) {
	if strings.TrimSpace(noop.CircleID) == "" ||
		strings.TrimSpace(noop.ReceiptKey) == "" ||
		strings.TrimSpace(noop.CommandDigest) == "" {
		return circleports.CommitReceipt{}, circlemodel.ErrInvalidChange
	}
	if replay, found, err := store.findReceipt(ctx, noop.ReceiptKey, noop.CommandDigest); err != nil || found {
		return replay, err
	}
	expiresAt := noop.ReceiptExpiresAt.UTC()
	if expiresAt.IsZero() {
		expiresAt = time.Now().UTC().Add(24 * time.Hour)
	}
	_, err := store.receipts.InsertOne(ctx, bson.M{
		"_id": noop.ReceiptKey, "commandDigest": noop.CommandDigest,
		"circleId": noop.CircleID, "version": noop.Version, "status": noop.Status,
		"expiresAt": expiresAt,
	})
	if err != nil {
		if mongo.IsDuplicateKeyError(err) {
			if replay, found, replayErr := store.findReceipt(ctx, noop.ReceiptKey, noop.CommandDigest); replayErr == nil && found {
				return replay, nil
			}
		}
		return circleports.CommitReceipt{}, err
	}
	return circleports.CommitReceipt{
		CircleID: noop.CircleID, Version: noop.Version, Status: noop.Status,
	}, nil
}

func (store *MongoAggregateStore) findReceipt(ctx context.Context, receiptKey, commandDigest string) (circleports.CommitReceipt, bool, error) {
	var document struct {
		CommandDigest string                   `bson:"commandDigest"`
		CircleID      string                   `bson:"circleId"`
		Version       int64                    `bson:"version"`
		Status        circlemodel.CircleStatus `bson:"status"`
	}
	err := store.receipts.FindOne(ctx, bson.M{"_id": receiptKey}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return circleports.CommitReceipt{}, false, nil
	}
	if err != nil {
		return circleports.CommitReceipt{}, false, err
	}
	if document.CommandDigest != commandDigest {
		return circleports.CommitReceipt{}, false, circlemodel.ErrIdempotencyConflict
	}
	return circleports.CommitReceipt{
		CircleID: document.CircleID, Version: document.Version, Status: document.Status, Replayed: true,
	}, true, nil
}

// ReadAfter/LoadCheckpoint/SaveCheckpoint 供 Circle 本体 outbox relay 消费。
func (store *MongoAggregateStore) ReadAfter(ctx context.Context, checkpoint string, limit int) ([]circleports.OutboxEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	filter := bson.M{}
	if strings.TrimSpace(checkpoint) != "" {
		after, err := strconv.ParseInt(strings.TrimSpace(checkpoint), 10, 64)
		if err != nil {
			return nil, err
		}
		filter["outboxSequence"] = bson.M{"$gt": after}
	}
	cursor, err := store.outbox.Find(ctx, filter,
		options.Find().SetSort(bson.D{{Key: "outboxSequence", Value: 1}}).SetLimit(int64(limit)))
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var events []circleports.OutboxEvent
	for cursor.Next(ctx) {
		var document struct {
			ID               string    `bson:"_id"`
			OutboxSequence   int64     `bson:"outboxSequence"`
			EventType        string    `bson:"eventType"`
			AggregateID      string    `bson:"aggregateId"`
			AggregateVersion int64     `bson:"aggregateVersion"`
			PayloadJSON      string    `bson:"payloadJson"`
			OccurredAt       time.Time `bson:"occurredAt"`
		}
		if err := cursor.Decode(&document); err != nil {
			return nil, err
		}
		events = append(events, circleports.OutboxEvent{
			EventID:          document.ID,
			EventType:        document.EventType,
			AggregateID:      document.AggregateID,
			AggregateVersion: document.AggregateVersion,
			Payload:          json.RawMessage(document.PayloadJSON),
			OccurredAt:       document.OccurredAt,
			Checkpoint:       strconv.FormatInt(document.OutboxSequence, 10),
		})
	}
	return events, cursor.Err()
}

func (store *MongoAggregateStore) LoadCheckpoint(ctx context.Context, consumer string) (string, error) {
	var document struct {
		Checkpoint string `bson:"checkpoint"`
	}
	err := store.checkpoints.FindOne(ctx, bson.M{"_id": strings.TrimSpace(consumer)}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	return document.Checkpoint, nil
}

func (store *MongoAggregateStore) SaveCheckpoint(ctx context.Context, consumer, checkpoint string) error {
	_, err := store.checkpoints.UpdateOne(ctx,
		bson.M{"_id": strings.TrimSpace(consumer)},
		bson.M{"$set": bson.M{"checkpoint": checkpoint, "updatedAt": time.Now().UTC()}},
		options.UpdateOne().SetUpsert(true))
	return err
}

func circleEventType(kind circlemodel.ChangeKind) string {
	switch kind {
	case circlemodel.ChangeCreate:
		return "CircleCreated"
	case circlemodel.ChangeArchive:
		return "CircleArchived"
	case circlemodel.ChangeSections:
		return "CircleSectionsUpdated"
	default:
		return "CircleUpdated"
	}
}

func circleEventPayloadFor(eventType string, circle circlemodel.Circle) map[string]any {
	switch eventType {
	case "CircleCreated":
		return map[string]any{
			"id": circle.ID, "name": circle.Name, "ownerId": circle.OwnerID,
			"category": circle.Category, "tags": circle.Tags,
			"rulesText": circle.RulesText, "welcomeMessage": circle.WelcomeMessage,
			"iconUrl": circle.IconUrl, "autoSyncChat": circle.AutoSyncChat,
		}
	case "CircleArchived":
		return map[string]any{"id": circle.ID, "status": circle.Status}
	case "CircleSectionsUpdated":
		return map[string]any{"circleId": circle.ID, "sectionConfig": circle.SectionConfig}
	default:
		return map[string]any{
			"id": circle.ID, "name": circle.Name, "description": circle.Description,
			"rulesText": circle.RulesText, "welcomeMessage": circle.WelcomeMessage,
			"iconUrl": circle.IconUrl, "autoSyncChat": circle.AutoSyncChat,
			"tags": circle.Tags, "category": circle.Category,
		}
	}
}

var (
	_ circleports.AggregateStore            = (*MongoAggregateStore)(nil)
	_ circleports.OutboxReader              = (*MongoAggregateStore)(nil)
	_ circleports.ProjectionCheckpointStore = (*MongoAggregateStore)(nil)
)
