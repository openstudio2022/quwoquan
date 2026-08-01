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

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
)

const (
	gatheringCollection = "gatherings"
	receiptCollection   = "gathering_command_receipts"
	outboxCollection    = "gathering_outbox"
	sequenceCollection  = "gathering_outbox_sequences"
)

type MongoAggregateStore struct {
	gatherings *mongo.Collection
	receipts   *mongo.Collection
	outbox     *mongo.Collection
	sequences  *mongo.Collection
}

func NewMongoAggregateStore(database *mongo.Database) *MongoAggregateStore {
	if database == nil {
		panic("Gathering MongoAggregateStore requires database")
	}
	return &MongoAggregateStore{
		gatherings: database.Collection(gatheringCollection),
		receipts:   database.Collection(receiptCollection),
		outbox:     database.Collection(outboxCollection),
		sequences:  database.Collection(sequenceCollection),
	}
}

func (store *MongoAggregateStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.gatherings.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "conversationId", Value: 1}}, Options: options.Index().SetName("uq_gathering_conversation").SetSparse(true).SetUnique(true)},
		{Keys: bson.D{{Key: "status", Value: 1}, {Key: "startAt", Value: 1}}, Options: options.Index().SetName("idx_gathering_status_start")},
	}); err != nil {
		return err
	}
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "expiresAt", Value: 1}}, Options: options.Index().SetName("ttl_gathering_command_receipts").SetExpireAfterSeconds(0),
	}); err != nil {
		return err
	}
	_, err := store.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}}, Options: options.Index().SetName("uq_gathering_outbox_version").SetUnique(true)},
		{Keys: bson.D{{Key: "outboxSequence", Value: 1}}, Options: options.Index().SetName("uq_gathering_outbox_sequence").SetUnique(true)},
	})
	return err
}

func (store *MongoAggregateStore) Load(ctx context.Context, gatheringID string) (model.Gathering, bool, error) {
	var value model.Gathering
	err := store.gatherings.FindOne(ctx, bson.M{"_id": strings.TrimSpace(gatheringID)}).Decode(&value)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Gathering{}, false, nil
	}
	if err != nil {
		return model.Gathering{}, false, err
	}
	return value, true, nil
}

func (store *MongoAggregateStore) Commit(ctx context.Context, request ports.CommitRequest) (ports.CommitReceipt, error) {
	if strings.TrimSpace(request.GatheringID) == "" || strings.TrimSpace(request.ReceiptKey) == "" ||
		strings.TrimSpace(request.CommandDigest) == "" || request.ReceiptExpiresAt.IsZero() ||
		strings.TrimSpace(request.EventType) == "" || request.Mutate == nil {
		return ports.CommitReceipt{}, model.ErrInvalidArgument
	}
	if replay, found, err := store.findReceipt(ctx, request.ReceiptKey, request.CommandDigest); err != nil || found {
		return replay, err
	}
	session, err := store.gatherings.Database().Client().StartSession()
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	defer session.EndSession(ctx)
	var committed ports.CommitReceipt
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if replay, found, findErr := store.findReceipt(txCtx, request.ReceiptKey, request.CommandDigest); findErr != nil {
			return nil, findErr
		} else if found {
			committed = replay
			return nil, nil
		}
		current, found, loadErr := store.Load(txCtx, request.GatheringID)
		if loadErr != nil {
			return nil, loadErr
		}
		var currentPointer *model.Gathering
		if found {
			copy := current
			currentPointer = &copy
		}
		next, mutateErr := request.Mutate(currentPointer)
		if mutateErr != nil {
			return nil, mutateErr
		}
		if next.ID != request.GatheringID {
			return nil, model.ErrInvalidArgument
		}
		changed := !found || next.Version != current.Version
		if !found {
			if _, insertErr := store.gatherings.InsertOne(txCtx, next); insertErr != nil {
				if mongo.IsDuplicateKeyError(insertErr) {
					return nil, ports.ErrVersionConflict
				}
				return nil, insertErr
			}
		} else if changed {
			result, replaceErr := store.gatherings.ReplaceOne(txCtx, bson.M{"_id": next.ID, "version": current.Version}, next)
			if replaceErr != nil {
				if mongo.IsDuplicateKeyError(replaceErr) {
					return nil, ports.ErrVersionConflict
				}
				return nil, replaceErr
			}
			if result.MatchedCount != 1 {
				return nil, ports.ErrVersionConflict
			}
		}
		if changed {
			if outboxErr := store.appendOutbox(txCtx, request.EventType, next); outboxErr != nil {
				return nil, outboxErr
			}
		}
		_, insertErr := store.receipts.InsertOne(txCtx, bson.M{
			"_id": request.ReceiptKey, "commandDigest": request.CommandDigest,
			"gatheringId": next.ID, "version": next.Version, "status": next.Status,
			"aggregateSnapshot": next, "expiresAt": request.ReceiptExpiresAt.UTC(),
		})
		if mongo.IsDuplicateKeyError(insertErr) {
			return nil, gatheringerrors.ErrGatheringIdempotencyConflict
		}
		if insertErr != nil {
			return nil, insertErr
		}
		committed = ports.CommitReceipt{Gathering: next}
		return nil, nil
	})
	return committed, err
}

func (store *MongoAggregateStore) findReceipt(ctx context.Context, key, digest string) (ports.CommitReceipt, bool, error) {
	var receipt struct {
		CommandDigest     string          `bson:"commandDigest"`
		AggregateSnapshot model.Gathering `bson:"aggregateSnapshot"`
	}
	err := store.receipts.FindOne(ctx, bson.M{"_id": key}).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return ports.CommitReceipt{}, false, nil
	}
	if err != nil {
		return ports.CommitReceipt{}, false, err
	}
	if receipt.CommandDigest != digest {
		return ports.CommitReceipt{}, false, gatheringerrors.ErrGatheringIdempotencyConflict
	}
	return ports.CommitReceipt{Gathering: receipt.AggregateSnapshot, Replayed: true}, true, nil
}

func (store *MongoAggregateStore) appendOutbox(ctx context.Context, eventType string, value model.Gathering) error {
	var sequence struct {
		Value int64 `bson:"value"`
	}
	if err := store.sequences.FindOneAndUpdate(
		ctx, bson.M{"_id": "Gathering"}, bson.M{"$inc": bson.M{"value": int64(1)}},
		options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
	).Decode(&sequence); err != nil {
		return err
	}
	payload, err := json.Marshal(value)
	if err != nil {
		return err
	}
	eventID := value.ID + ":" + eventType + ":" + strconv.FormatInt(value.Version, 10)
	_, err = store.outbox.InsertOne(ctx, bson.M{
		"_id": eventID, "outboxSequence": sequence.Value, "eventType": eventType,
		"aggregateId": value.ID, "aggregateVersion": value.Version,
		"payloadJson": string(payload), "occurredAt": value.UpdatedAt.UTC(),
	})
	return err
}

var _ ports.AggregateStore = (*MongoAggregateStore)(nil)

var _ = time.Now
