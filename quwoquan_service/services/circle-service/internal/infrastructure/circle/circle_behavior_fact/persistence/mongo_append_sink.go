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

	behaviorfactmodel "quwoquan_service/services/circle-service/internal/domain/circle/circle_behavior_fact/model"
	behaviorfactports "quwoquan_service/services/circle-service/internal/domain/circle/circle_behavior_fact/ports"
)

const (
	behaviorFactCollection       = "circle_behavior_facts"
	behaviorOutboxCollection     = "circle_behavior_fact_outbox"
	behaviorSequenceCollection   = "circle_behavior_fact_outbox_sequences"
	behaviorCheckpointCollection = "circle_behavior_fact_projection_checkpoints"
)

type MongoAppendSink struct {
	facts       *mongo.Collection
	outbox      *mongo.Collection
	sequences   *mongo.Collection
	checkpoints *mongo.Collection
	circles     *mongo.Collection
}

func NewMongoAppendSink(database *mongo.Database) *MongoAppendSink {
	if database == nil {
		panic("CircleBehaviorFact MongoAppendSink requires database")
	}
	return &MongoAppendSink{
		facts: database.Collection(behaviorFactCollection), outbox: database.Collection(behaviorOutboxCollection),
		sequences: database.Collection(behaviorSequenceCollection), checkpoints: database.Collection(behaviorCheckpointCollection),
		circles: database.Collection("circles"),
	}
}

func (sink *MongoAppendSink) EnsureIndexes(ctx context.Context) error {
	if _, err := sink.facts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "circleId", Value: 1}, {Key: "occurredAt", Value: -1}}, Options: options.Index().SetName("idx_circle_behavior_circle_time")},
		{Keys: bson.D{{Key: "personaId", Value: 1}, {Key: "occurredAt", Value: -1}}, Options: options.Index().SetName("idx_circle_behavior_persona_time")},
		{Keys: bson.D{{Key: "deviceActorId", Value: 1}, {Key: "occurredAt", Value: -1}}, Options: options.Index().SetName("idx_circle_behavior_device_time")},
	}); err != nil {
		return err
	}
	_, err := sink.outbox.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "outboxSequence", Value: 1}}, Options: options.Index().SetName("idx_circle_behavior_outbox_sequence").SetUnique(true),
	})
	return err
}

func (sink *MongoAppendSink) ReadCircleState(ctx context.Context, circleID string) (string, bool, error) {
	var document struct {
		State string `bson:"status"`
	}
	err := sink.circles.FindOne(ctx, bson.M{"_id": strings.TrimSpace(circleID)}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return "", false, nil
	}
	if err != nil {
		return "", false, err
	}
	return document.State, true, nil
}

func (sink *MongoAppendSink) Append(ctx context.Context, request behaviorfactports.AppendRequest) (behaviorfactports.AppendReceipt, error) {
	if strings.TrimSpace(request.Fact.ID) == "" || strings.TrimSpace(request.CommandDigest) == "" ||
		strings.TrimSpace(request.Fact.CircleID) == "" || request.Fact.OccurredAt.IsZero() {
		return behaviorfactports.AppendReceipt{}, behaviorfactmodel.ErrInvalidFact
	}
	if replay, found, err := sink.findFact(ctx, request.Fact.ID, request.CommandDigest); err != nil || found {
		return replay, err
	}
	session, err := sink.facts.Database().Client().StartSession()
	if err != nil {
		return behaviorfactports.AppendReceipt{}, err
	}
	defer session.EndSession(ctx)
	receipt := behaviorfactports.AppendReceipt{FactID: request.Fact.ID}
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if replay, found, findErr := sink.findFact(txCtx, request.Fact.ID, request.CommandDigest); findErr != nil {
			return nil, findErr
		} else if found {
			receipt = replay
			return nil, nil
		}
		document := bson.M{
			"_id": request.Fact.ID, "actorKind": request.Fact.ActorKind,
			"personaId": request.Fact.PersonaID, "deviceActorId": request.Fact.DeviceActorID,
			"circleId": request.Fact.CircleID, "eventType": request.Fact.EventType,
			"sessionId": request.Fact.SessionID, "requestId": request.Fact.RequestID,
			"occurredAt": request.Fact.OccurredAt.UTC(), "commandDigest": request.CommandDigest,
		}
		if _, insertErr := sink.facts.InsertOne(txCtx, document); insertErr != nil {
			if mongo.IsDuplicateKeyError(insertErr) {
				return nil, behaviorfactmodel.ErrIdempotencyConflict
			}
			return nil, insertErr
		}
		var sequence struct {
			Value int64 `bson:"value"`
		}
		if sequenceErr := sink.sequences.FindOneAndUpdate(txCtx,
			bson.M{"_id": "CircleBehaviorFact"}, bson.M{"$inc": bson.M{"value": int64(1)}},
			options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After)).Decode(&sequence); sequenceErr != nil {
			return nil, sequenceErr
		}
		payload, marshalErr := json.Marshal(request.Fact)
		if marshalErr != nil {
			return nil, marshalErr
		}
		_, insertErr := sink.outbox.InsertOne(txCtx, bson.M{
			"_id":            request.Fact.ID + ":CircleBehaviorFactAppended",
			"outboxSequence": sequence.Value, "eventType": "CircleBehaviorFactAppended",
			"aggregateId": request.Fact.ID, "payloadJson": string(payload),
			"occurredAt": request.Fact.OccurredAt.UTC(),
		})
		return nil, insertErr
	})
	if err != nil {
		if replay, found, findErr := sink.findFact(ctx, request.Fact.ID, request.CommandDigest); findErr == nil && found {
			return replay, nil
		}
		return behaviorfactports.AppendReceipt{}, err
	}
	return receipt, nil
}

func (sink *MongoAppendSink) findFact(ctx context.Context, factID, digest string) (behaviorfactports.AppendReceipt, bool, error) {
	var document struct {
		CommandDigest string `bson:"commandDigest"`
	}
	err := sink.facts.FindOne(ctx, bson.M{"_id": strings.TrimSpace(factID)}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return behaviorfactports.AppendReceipt{}, false, nil
	}
	if err != nil {
		return behaviorfactports.AppendReceipt{}, false, err
	}
	if document.CommandDigest != digest {
		return behaviorfactports.AppendReceipt{}, false, behaviorfactmodel.ErrIdempotencyConflict
	}
	return behaviorfactports.AppendReceipt{FactID: factID, Replayed: true}, true, nil
}

func (sink *MongoAppendSink) ReadAfter(ctx context.Context, checkpoint string, limit int) ([]behaviorfactports.OutboxEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	if limit > 1000 {
		limit = 1000
	}
	filter := bson.M{}
	if checkpoint = strings.TrimSpace(checkpoint); checkpoint != "" {
		sequence, err := parseBehaviorCheckpoint(checkpoint)
		if err != nil {
			return nil, err
		}
		filter["outboxSequence"] = bson.M{"$gt": sequence}
	}
	rows, err := sink.outbox.Find(ctx, filter, options.Find().SetSort(bson.D{{Key: "outboxSequence", Value: 1}}).SetLimit(int64(limit)))
	if err != nil {
		return nil, err
	}
	defer rows.Close(ctx)
	var result []behaviorfactports.OutboxEvent
	for rows.Next(ctx) {
		var document struct {
			ID          string    `bson:"_id"`
			Sequence    int64     `bson:"outboxSequence"`
			EventType   string    `bson:"eventType"`
			AggregateID string    `bson:"aggregateId"`
			PayloadJSON string    `bson:"payloadJson"`
			OccurredAt  time.Time `bson:"occurredAt"`
		}
		if err := rows.Decode(&document); err != nil {
			return nil, err
		}
		payload := json.RawMessage(document.PayloadJSON)
		if !json.Valid(payload) {
			return nil, behaviorfactmodel.ErrInvalidFact
		}
		result = append(result, behaviorfactports.OutboxEvent{
			EventID: document.ID, EventType: document.EventType, AggregateID: document.AggregateID,
			Payload: append(json.RawMessage(nil), payload...), OccurredAt: document.OccurredAt.UTC(),
			Checkpoint: strconv.FormatInt(document.Sequence, 10),
		})
	}
	return result, rows.Err()
}

func (sink *MongoAppendSink) LoadCheckpoint(ctx context.Context, consumer string) (string, error) {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return "", behaviorfactmodel.ErrInvalidFact
	}
	var document struct {
		Sequence int64 `bson:"sequence"`
	}
	err := sink.checkpoints.FindOne(ctx, bson.M{"_id": "circle-behavior-fact:" + consumer}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	if document.Sequence <= 0 {
		return "", nil
	}
	return strconv.FormatInt(document.Sequence, 10), nil
}

func (sink *MongoAppendSink) SaveCheckpoint(ctx context.Context, consumer, checkpoint string) error {
	sequence, err := parseBehaviorCheckpoint(checkpoint)
	if err != nil || strings.TrimSpace(consumer) == "" {
		return behaviorfactmodel.ErrInvalidFact
	}
	_, err = sink.checkpoints.UpdateOne(ctx, bson.M{"_id": "circle-behavior-fact:" + strings.TrimSpace(consumer)},
		bson.M{"$max": bson.M{"sequence": sequence}, "$set": bson.M{"updatedAt": time.Now().UTC()}},
		options.UpdateOne().SetUpsert(true))
	return err
}

func parseBehaviorCheckpoint(value string) (int64, error) {
	sequence, err := strconv.ParseInt(strings.TrimSpace(value), 10, 64)
	if err != nil || sequence <= 0 {
		return 0, behaviorfactmodel.ErrInvalidFact
	}
	return sequence, nil
}

var (
	_ behaviorfactports.AppendSink                = (*MongoAppendSink)(nil)
	_ behaviorfactports.CircleStateReader         = (*MongoAppendSink)(nil)
	_ behaviorfactports.OutboxReader              = (*MongoAppendSink)(nil)
	_ behaviorfactports.ProjectionCheckpointStore = (*MongoAppendSink)(nil)
)
