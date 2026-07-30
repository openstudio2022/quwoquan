package persistence

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	sharemodel "quwoquan_service/services/content-service/internal/content/outbound_share_fact/domain/model"
	shareports "quwoquan_service/services/content-service/internal/content/outbound_share_fact/domain/ports"
)

const (
	outboundShareFactCollection       = "outbound_share_facts"
	outboundShareReceiptCollection    = "outbound_share_receipts"
	outboundShareOutboxCollection     = "outbound_share_outbox"
	outboundShareSequenceCollection   = "outbound_share_outbox_sequences"
	outboundShareCheckpointCollection = "outbound_share_projection_checkpoints"
)

type factDocument struct {
	EventID           string                     `bson:"_id"`
	PostID            string                     `bson:"postId"`
	ActorDimension    sharemodel.ActorDimension  `bson:"actorDimension"`
	ActorID           string                     `bson:"actorId"`
	Channel           sharemodel.Channel         `bson:"channel"`
	DestinationKind   sharemodel.DestinationKind `bson:"destinationKind"`
	DestinationDigest string                     `bson:"destinationDigest,omitempty"`
	ReferralID        string                     `bson:"referralId"`
	IdempotencyKey    string                     `bson:"idempotencyKey"`
	OccurredAt        bson.DateTime              `bson:"occurredAt"`
}

type receiptDocument struct {
	ID            string       `bson:"_id"`
	CommandDigest string       `bson:"commandDigest"`
	Fact          factDocument `bson:"fact"`
}

type outboxDocument struct {
	EventID        string        `bson:"_id"`
	EventKey       string        `bson:"eventId"`
	EventType      string        `bson:"eventType"`
	Payload        []byte        `bson:"payload"`
	OccurredAt     bson.DateTime `bson:"occurredAt"`
	OutboxSequence int64         `bson:"outboxSequence"`
}

type sequenceDocument struct {
	ID       string `bson:"_id"`
	Sequence int64  `bson:"sequence"`
}

type checkpointDocument struct {
	ID        string    `bson:"_id"`
	Consumer  string    `bson:"consumer"`
	Sequence  int64     `bson:"sequence"`
	UpdatedAt time.Time `bson:"updatedAt"`
}

type MongoAppendSink struct {
	facts       *mongo.Collection
	receipts    *mongo.Collection
	outbox      *mongo.Collection
	sequences   *mongo.Collection
	checkpoints *mongo.Collection
}

var _ shareports.AppendSink = (*MongoAppendSink)(nil)

func NewMongoAppendSink(db *mongo.Database) *MongoAppendSink {
	if db == nil {
		panic("OutboundShareFact MongoAppendSink requires database")
	}
	return &MongoAppendSink{
		facts:       db.Collection(outboundShareFactCollection),
		receipts:    db.Collection(outboundShareReceiptCollection),
		outbox:      db.Collection(outboundShareOutboxCollection),
		sequences:   db.Collection(outboundShareSequenceCollection),
		checkpoints: db.Collection(outboundShareCheckpointCollection),
	}
}

func (s *MongoAppendSink) EnsureIndexes(ctx context.Context) error {
	if _, err := s.facts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "actorDimension", Value: 1}, {Key: "actorId", Value: 1}, {Key: "idempotencyKey", Value: 1}}, Options: options.Index().SetName("idx_outbound_share_dedupe").SetUnique(true)},
		{Keys: bson.D{{Key: "postId", Value: 1}, {Key: "occurredAt", Value: -1}}, Options: options.Index().SetName("idx_outbound_share_post_time")},
	}); err != nil {
		return err
	}
	if _, err := s.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "eventId", Value: 1}},
			Options: options.Index().SetName("idx_outbound_share_outbox_event").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "outboxSequence", Value: 1}},
			Options: options.Index().SetName("idx_outbound_share_outbox_sequence").SetUnique(true),
		},
	}); err != nil {
		return err
	}
	_, err := s.checkpoints.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "consumer", Value: 1}},
		Options: options.Index().SetName("idx_outbound_share_projection_checkpoint_consumer").SetUnique(true),
	})
	return err
}

func (s *MongoAppendSink) CountByPost(
	ctx context.Context,
	postID string,
) (int64, error) {
	if s == nil || s.facts == nil {
		return 0, errors.New("OutboundShareFact count reader is not configured")
	}
	postID = strings.TrimSpace(postID)
	if postID == "" {
		return 0, errors.New("OutboundShareFact count requires postId")
	}
	return s.facts.CountDocuments(ctx, bson.M{"postId": postID})
}

func (s *MongoAppendSink) Append(ctx context.Context, request shareports.AppendRequest) (shareports.AppendResult, error) {
	if err := request.Fact.Validate(); err != nil {
		return shareports.AppendResult{}, err
	}
	if strings.TrimSpace(request.CommandDigest) == "" || strings.TrimSpace(request.Outbox.EventID) != request.Fact.EventID {
		return shareports.AppendResult{}, errors.New("outbound share append requires matching command digest and outbox event")
	}
	if replay, found, err := s.findReceipt(ctx, request.Fact.IdempotencyKey, request.CommandDigest); err != nil || found {
		return replay, err
	}
	session, err := s.facts.Database().Client().StartSession()
	if err != nil {
		return shareports.AppendResult{}, err
	}
	defer session.EndSession(ctx)

	result := shareports.AppendResult{Fact: request.Fact}
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if replay, found, findErr := s.findReceipt(txCtx, request.Fact.IdempotencyKey, request.CommandDigest); findErr != nil {
			return nil, findErr
		} else if found {
			result = replay
			return nil, nil
		}
		fact := factDocumentFrom(request.Fact)
		if _, insertErr := s.facts.InsertOne(txCtx, fact); insertErr != nil {
			return nil, insertErr
		}
		sequence, sequenceErr := s.nextSequence(txCtx)
		if sequenceErr != nil {
			return nil, sequenceErr
		}
		if _, insertErr := s.outbox.InsertOne(txCtx, outboxDocument{
			EventID: request.Outbox.EventID, EventKey: request.Outbox.EventID,
			EventType: request.Outbox.EventType, Payload: request.Outbox.Payload,
			OccurredAt:     bson.NewDateTimeFromTime(request.Outbox.OccurredAt.UTC()),
			OutboxSequence: sequence,
		}); insertErr != nil {
			return nil, insertErr
		}
		_, insertErr := s.receipts.InsertOne(txCtx, receiptDocument{
			ID: request.Fact.IdempotencyKey, CommandDigest: request.CommandDigest, Fact: fact,
		})
		return nil, insertErr
	})
	if err != nil {
		// Mongo may report UnknownTransactionCommitResult after the transaction
		// has committed. The idempotency receipt is the authoritative outcome.
		if replay, found, replayErr := s.findReceipt(
			ctx,
			request.Fact.IdempotencyKey,
			request.CommandDigest,
		); replayErr == nil && found {
			return replay, nil
		}
		return shareports.AppendResult{}, err
	}
	return result, nil
}

func (s *MongoAppendSink) findReceipt(ctx context.Context, idempotencyKey, commandDigest string) (shareports.AppendResult, bool, error) {
	var receipt receiptDocument
	err := s.receipts.FindOne(ctx, bson.D{{Key: "_id", Value: strings.TrimSpace(idempotencyKey)}}).Decode(&receipt)
	if err == mongo.ErrNoDocuments {
		return shareports.AppendResult{}, false, nil
	}
	if err != nil {
		return shareports.AppendResult{}, false, err
	}
	if receipt.CommandDigest != commandDigest {
		return shareports.AppendResult{}, false, contentgenerated.AppErrorFromIdempotencyConflict("outbound share idempotency key reused with another command")
	}
	return shareports.AppendResult{Fact: factFromDocument(receipt.Fact), Replayed: true}, true, nil
}

func (s *MongoAppendSink) nextSequence(ctx context.Context) (int64, error) {
	var document sequenceDocument
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
		return 0, fmt.Errorf("OutboundShareFact outbox sequence did not advance")
	}
	return document.Sequence, nil
}

func (s *MongoAppendSink) ReadAfter(
	ctx context.Context,
	checkpoint string,
	limit int,
) ([]shareports.OutboxEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	filter := bson.M{}
	if strings.TrimSpace(checkpoint) != "" {
		sequence, err := parseOutboundShareCheckpoint(checkpoint)
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
	var documents []outboxDocument
	if err := cursor.All(ctx, &documents); err != nil {
		return nil, err
	}
	events := make([]shareports.OutboxEvent, 0, len(documents))
	for _, document := range documents {
		events = append(events, shareports.OutboxEvent{
			EventID:    document.EventID,
			EventType:  document.EventType,
			Payload:    append([]byte(nil), document.Payload...),
			OccurredAt: document.OccurredAt.Time().UTC(),
			Checkpoint: strconv.FormatInt(document.OutboxSequence, 10),
		})
	}
	return events, nil
}

func (s *MongoAppendSink) LoadCheckpoint(
	ctx context.Context,
	consumer string,
) (string, error) {
	var document checkpointDocument
	err := s.checkpoints.FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(consumer)},
	).Decode(&document)
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

func (s *MongoAppendSink) SaveCheckpoint(
	ctx context.Context,
	consumer string,
	checkpoint string,
) error {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return fmt.Errorf("OutboundShareFact checkpoint consumer is required")
	}
	sequence, err := parseOutboundShareCheckpoint(checkpoint)
	if err != nil {
		return err
	}
	_, err = s.checkpoints.UpdateOne(
		ctx,
		bson.M{"_id": consumer},
		bson.M{
			"$max": bson.M{"sequence": sequence},
			"$set": bson.M{
				"consumer":  consumer,
				"updatedAt": time.Now().UTC(),
			},
		},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

func parseOutboundShareCheckpoint(checkpoint string) (int64, error) {
	sequence, err := strconv.ParseInt(strings.TrimSpace(checkpoint), 10, 64)
	if err != nil || sequence <= 0 {
		return 0, fmt.Errorf("invalid OutboundShareFact checkpoint")
	}
	return sequence, nil
}

func factDocumentFrom(fact sharemodel.Fact) factDocument {
	return factDocument{
		EventID: fact.EventID, PostID: fact.PostID, ActorDimension: fact.ActorDimension,
		ActorID: fact.ActorID, Channel: fact.Channel, DestinationKind: fact.DestinationKind,
		DestinationDigest: fact.DestinationDigest, ReferralID: fact.ReferralID,
		IdempotencyKey: fact.IdempotencyKey, OccurredAt: bson.NewDateTimeFromTime(fact.OccurredAt.UTC()),
	}
}

var (
	_ shareports.OutboxReader              = (*MongoAppendSink)(nil)
	_ shareports.ProjectionCheckpointStore = (*MongoAppendSink)(nil)
)

func factFromDocument(document factDocument) sharemodel.Fact {
	return sharemodel.Fact{
		EventID: document.EventID, PostID: document.PostID, ActorDimension: document.ActorDimension,
		ActorID: document.ActorID, Channel: document.Channel, DestinationKind: document.DestinationKind,
		DestinationDigest: document.DestinationDigest, ReferralID: document.ReferralID,
		IdempotencyKey: document.IdempotencyKey, OccurredAt: document.OccurredAt.Time().UTC(),
	}
}
