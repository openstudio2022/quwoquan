package persistence

import (
	"context"
	"errors"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	sharemodel "quwoquan_service/services/content-service/internal/domain/content/outbound_share_fact/model"
	shareports "quwoquan_service/services/content-service/internal/domain/content/outbound_share_fact/ports"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

const (
	outboundShareFactCollection    = "outbound_share_facts"
	outboundShareReceiptCollection = "outbound_share_receipts"
	outboundShareOutboxCollection  = "outbound_share_outbox"
)

type factDocument struct {
	EventID           string                    `bson:"_id"`
	PostID            string                    `bson:"postId"`
	ActorDimension    sharemodel.ActorDimension `bson:"actorDimension"`
	ActorID           string                    `bson:"actorId"`
	Channel           string                    `bson:"channel"`
	DestinationKind   string                    `bson:"destinationKind"`
	DestinationDigest string                    `bson:"destinationDigest,omitempty"`
	ReferralID        string                    `bson:"referralId"`
	IdempotencyKey    string                    `bson:"idempotencyKey"`
	OccurredAt        bson.DateTime             `bson:"occurredAt"`
}

type receiptDocument struct {
	ID            string       `bson:"_id"`
	CommandDigest string       `bson:"commandDigest"`
	Fact          factDocument `bson:"fact"`
}

type outboxDocument struct {
	EventID    string        `bson:"_id"`
	EventType  string        `bson:"eventType"`
	Payload    []byte        `bson:"payload"`
	OccurredAt bson.DateTime `bson:"occurredAt"`
}

type MongoAppendSink struct {
	facts    *mongo.Collection
	receipts *mongo.Collection
	outbox   *mongo.Collection
}

var _ shareports.AppendSink = (*MongoAppendSink)(nil)

func NewMongoAppendSink(db *mongo.Database) *MongoAppendSink {
	if db == nil {
		panic("OutboundShareFact MongoAppendSink requires database")
	}
	return &MongoAppendSink{
		facts:    db.Collection(outboundShareFactCollection),
		receipts: db.Collection(outboundShareReceiptCollection),
		outbox:   db.Collection(outboundShareOutboxCollection),
	}
}

func (s *MongoAppendSink) EnsureIndexes(ctx context.Context) error {
	if _, err := s.facts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "actorDimension", Value: 1}, {Key: "actorId", Value: 1}, {Key: "idempotencyKey", Value: 1}}, Options: options.Index().SetName("idx_outbound_share_dedupe").SetUnique(true)},
		{Keys: bson.D{{Key: "postId", Value: 1}, {Key: "occurredAt", Value: -1}}, Options: options.Index().SetName("idx_outbound_share_post_time")},
	}); err != nil {
		return err
	}
	_, err := s.outbox.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "occurredAt", Value: 1}, {Key: "_id", Value: 1}},
		Options: options.Index().SetName("idx_outbound_share_outbox_replay"),
	})
	return err
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
		if _, insertErr := s.outbox.InsertOne(txCtx, outboxDocument{
			EventID: request.Outbox.EventID, EventType: request.Outbox.EventType,
			Payload: request.Outbox.Payload, OccurredAt: bson.NewDateTimeFromTime(request.Outbox.OccurredAt.UTC()),
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

func factDocumentFrom(fact sharemodel.Fact) factDocument {
	return factDocument{
		EventID: fact.EventID, PostID: fact.PostID, ActorDimension: fact.ActorDimension,
		ActorID: fact.ActorID, Channel: fact.Channel, DestinationKind: fact.DestinationKind,
		DestinationDigest: fact.DestinationDigest, ReferralID: fact.ReferralID,
		IdempotencyKey: fact.IdempotencyKey, OccurredAt: bson.NewDateTimeFromTime(fact.OccurredAt.UTC()),
	}
}

func factFromDocument(document factDocument) sharemodel.Fact {
	return sharemodel.Fact{
		EventID: document.EventID, PostID: document.PostID, ActorDimension: document.ActorDimension,
		ActorID: document.ActorID, Channel: document.Channel, DestinationKind: document.DestinationKind,
		DestinationDigest: document.DestinationDigest, ReferralID: document.ReferralID,
		IdempotencyKey: document.IdempotencyKey, OccurredAt: document.OccurredAt.Time().UTC(),
	}
}
