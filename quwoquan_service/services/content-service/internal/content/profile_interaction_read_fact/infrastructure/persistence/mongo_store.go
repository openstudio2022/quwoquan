package persistence

import (
	"context"
	"fmt"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	readfactmodel "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/domain/model"
	readfactports "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/domain/ports"
)

const (
	readFactCollection           = "profile_interaction_read_facts"
	readFactOutboxCollection     = "profile_interaction_read_fact_outbox"
	readFactSequenceCollection   = "profile_interaction_read_fact_outbox_sequences"
	readFactCheckpointCollection = "profile_interaction_read_fact_projection_checkpoints"
)

type readFactDocument struct {
	ID                 string `bson:"_id"`
	readfactmodel.Fact `bson:",inline"`
}

type readFactOutboxDocument struct {
	EventID        string    `bson:"_id"`
	EventKey       string    `bson:"eventId"`
	EventType      string    `bson:"eventType"`
	Payload        []byte    `bson:"payload"`
	OccurredAt     time.Time `bson:"occurredAt"`
	OutboxSequence int64     `bson:"outboxSequence"`
}

type readFactSequenceDocument struct {
	ID       string `bson:"_id"`
	Sequence int64  `bson:"sequence"`
}

type readFactCheckpointDocument struct {
	ID        string    `bson:"_id"`
	Consumer  string    `bson:"consumer"`
	Sequence  int64     `bson:"sequence"`
	UpdatedAt time.Time `bson:"updatedAt"`
}

type MongoReadFactStore struct {
	facts       *mongo.Collection
	outbox      *mongo.Collection
	sequences   *mongo.Collection
	checkpoints *mongo.Collection
}

func NewMongoReadFactStore(db *mongo.Database) *MongoReadFactStore {
	if db == nil {
		panic("ProfileInteractionReadFact Mongo store requires database")
	}
	return &MongoReadFactStore{
		facts:       db.Collection(readFactCollection),
		outbox:      db.Collection(readFactOutboxCollection),
		sequences:   db.Collection(readFactSequenceCollection),
		checkpoints: db.Collection(readFactCheckpointCollection),
	}
}

func (s *MongoReadFactStore) EnsureIndexes(ctx context.Context) error {
	if _, err := s.facts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "ownerPersonaId", Value: 1},
				{Key: "activityId", Value: 1},
				{Key: "state", Value: 1},
			},
			Options: options.Index().SetName("idx_profile_interaction_read_fact_semantic_key").SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "ownerPersonaId", Value: 1},
				{Key: "activityId", Value: 1},
				{Key: "occurredAt", Value: 1},
			},
			Options: options.Index().SetName("idx_profile_interaction_read_fact_activity"),
		},
	}); err != nil {
		return err
	}
	if _, err := s.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "eventId", Value: 1}},
			Options: options.Index().SetName("idx_profile_interaction_read_fact_outbox_event").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "outboxSequence", Value: 1}},
			Options: options.Index().SetName("idx_profile_interaction_read_fact_outbox_sequence").SetUnique(true),
		},
	}); err != nil {
		return err
	}
	_, err := s.checkpoints.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "consumer", Value: 1}},
		Options: options.Index().SetName("idx_profile_interaction_read_fact_checkpoint_consumer").SetUnique(true),
	})
	return err
}

func (s *MongoReadFactStore) Append(
	ctx context.Context,
	request readfactports.AppendRequest,
) (readfactports.AppendResult, error) {
	if err := request.Fact.Validate(); err != nil {
		return readfactports.AppendResult{}, err
	}
	if request.Outbox.EventID != request.Fact.FactID ||
		request.Outbox.EventType == "" ||
		request.Outbox.OccurredAt.IsZero() {
		return readfactports.AppendResult{}, fmt.Errorf("ProfileInteractionReadFact outbox identity mismatch")
	}
	if replay, found, err := s.find(ctx, request.Fact.FactID); err != nil || found {
		return readfactports.AppendResult{Fact: replay, Replayed: found}, err
	}
	session, err := s.facts.Database().Client().StartSession()
	if err != nil {
		return readfactports.AppendResult{}, err
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if _, err := s.facts.InsertOne(txCtx, readFactDocument{
			ID:   request.Fact.FactID,
			Fact: request.Fact,
		}); err != nil {
			return nil, err
		}
		sequence, err := s.nextSequence(txCtx)
		if err != nil {
			return nil, err
		}
		_, err = s.outbox.InsertOne(txCtx, readFactOutboxDocument{
			EventID:        request.Outbox.EventID,
			EventKey:       request.Outbox.EventID,
			EventType:      request.Outbox.EventType,
			Payload:        append([]byte(nil), request.Outbox.Payload...),
			OccurredAt:     request.Outbox.OccurredAt.UTC(),
			OutboxSequence: sequence,
		})
		return nil, err
	})
	if err != nil {
		if replay, found, replayErr := s.find(ctx, request.Fact.FactID); replayErr == nil && found {
			return readfactports.AppendResult{Fact: replay, Replayed: true}, nil
		}
		return readfactports.AppendResult{}, err
	}
	return readfactports.AppendResult{Fact: request.Fact}, nil
}

func (s *MongoReadFactStore) nextSequence(ctx context.Context) (int64, error) {
	var document readFactSequenceDocument
	err := s.sequences.FindOneAndUpdate(
		ctx,
		bson.M{"_id": "global"},
		bson.M{"$inc": bson.M{"sequence": 1}},
		options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
	).Decode(&document)
	if err != nil {
		return 0, err
	}
	if document.Sequence <= 0 {
		return 0, fmt.Errorf("ProfileInteractionReadFact outbox sequence did not advance")
	}
	return document.Sequence, nil
}

func (s *MongoReadFactStore) find(
	ctx context.Context,
	factID string,
) (readfactmodel.Fact, bool, error) {
	var document readFactDocument
	err := s.facts.FindOne(ctx, bson.M{"_id": strings.TrimSpace(factID)}).Decode(&document)
	if err == mongo.ErrNoDocuments {
		return readfactmodel.Fact{}, false, nil
	}
	if err != nil {
		return readfactmodel.Fact{}, false, err
	}
	return document.Fact, true, nil
}

func (s *MongoReadFactStore) ReadAfter(
	ctx context.Context,
	checkpoint string,
	limit int,
) ([]readfactports.OutboxEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	filter := bson.M{}
	if strings.TrimSpace(checkpoint) != "" {
		sequence, err := parseReadFactCheckpoint(checkpoint)
		if err != nil {
			return nil, err
		}
		filter["outboxSequence"] = bson.M{"$gt": sequence}
	}
	cursor, err := s.outbox.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{{Key: "outboxSequence", Value: 1}}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var documents []readFactOutboxDocument
	if err := cursor.All(ctx, &documents); err != nil {
		return nil, err
	}
	events := make([]readfactports.OutboxEvent, 0, len(documents))
	for _, document := range documents {
		events = append(events, readfactports.OutboxEvent{
			EventID:    document.EventID,
			EventType:  document.EventType,
			Payload:    append([]byte(nil), document.Payload...),
			OccurredAt: document.OccurredAt.UTC(),
			Checkpoint: strconv.FormatInt(document.OutboxSequence, 10),
		})
	}
	return events, nil
}

func (s *MongoReadFactStore) LoadCheckpoint(
	ctx context.Context,
	consumer string,
) (string, error) {
	var document readFactCheckpointDocument
	err := s.checkpoints.FindOne(ctx, bson.M{"_id": strings.TrimSpace(consumer)}).Decode(&document)
	if err == mongo.ErrNoDocuments {
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

func (s *MongoReadFactStore) SaveCheckpoint(
	ctx context.Context,
	consumer string,
	checkpoint string,
) error {
	sequence, err := parseReadFactCheckpoint(checkpoint)
	if err != nil {
		return err
	}
	_, err = s.checkpoints.UpdateOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(consumer)},
		bson.M{
			"$max": bson.M{"sequence": sequence},
			"$set": bson.M{
				"consumer":  strings.TrimSpace(consumer),
				"updatedAt": time.Now().UTC(),
			},
		},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

func parseReadFactCheckpoint(checkpoint string) (int64, error) {
	sequence, err := strconv.ParseInt(strings.TrimSpace(checkpoint), 10, 64)
	if err != nil || sequence <= 0 {
		return 0, fmt.Errorf("invalid ProfileInteractionReadFact checkpoint")
	}
	return sequence, nil
}

var (
	_ readfactports.AppendSink                = (*MongoReadFactStore)(nil)
	_ readfactports.OutboxReader              = (*MongoReadFactStore)(nil)
	_ readfactports.ProjectionCheckpointStore = (*MongoReadFactStore)(nil)
)
