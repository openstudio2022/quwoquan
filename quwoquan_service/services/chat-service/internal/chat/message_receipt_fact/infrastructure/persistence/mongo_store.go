package persistence

import (
	"context"
	"errors"
	"fmt"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	receiptapp "quwoquan_service/services/chat-service/internal/chat/message_receipt_fact/application"
	receiptmodel "quwoquan_service/services/chat-service/internal/chat/message_receipt_fact/domain/model"
)

type MongoStore struct {
	receipts *mongo.Collection
}

var _ receiptapp.Store = (*MongoStore)(nil)

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		panic("message receipt fact database is required")
	}
	return &MongoStore{receipts: database.Collection("message_receipts")}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	_, err := store.receipts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "messageId", Value: 1}, {Key: "userId", Value: 1}},
			Options: options.Index().SetName("uq_message_receipts_identity").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "conversationId", Value: 1}, {Key: "messageId", Value: 1}},
			Options: options.Index().SetName("idx_message_receipts_conversation_message"),
		},
	})
	if err != nil {
		return fmt.Errorf("ensure message receipt fact indexes: %w", err)
	}
	return nil
}

func (store *MongoStore) AppendIfAbsent(
	ctx context.Context,
	fact receiptmodel.Fact,
) (receiptmodel.Fact, bool, error) {
	if err := fact.Validate(); err != nil {
		return receiptmodel.Fact{}, false, err
	}
	_, err := store.receipts.InsertOne(ctx, fact)
	if err == nil {
		return fact, false, nil
	}
	if !mongo.IsDuplicateKeyError(err) {
		return receiptmodel.Fact{}, false, err
	}

	var committed receiptmodel.Fact
	findErr := store.receipts.FindOne(ctx, bson.M{
		"messageId": fact.MessageID,
		"userId":    fact.UserID,
	}).Decode(&committed)
	if findErr != nil {
		return receiptmodel.Fact{}, false, fmt.Errorf("load replayed message receipt fact: %w", findErr)
	}
	if !committed.SameImmutableValue(fact) {
		return receiptmodel.Fact{}, false, receiptmodel.ErrIdentityConflict
	}
	return committed, true, nil
}

func (store *MongoStore) ListByMessage(
	ctx context.Context,
	messageID string,
) ([]receiptmodel.Fact, error) {
	cursor, err := store.receipts.Find(
		ctx,
		bson.M{"messageId": messageID},
		options.Find().SetSort(bson.D{{Key: "readAt", Value: 1}, {Key: "_id", Value: 1}}),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	var receipts []receiptmodel.Fact
	if err := cursor.All(ctx, &receipts); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return []receiptmodel.Fact{}, nil
		}
		return nil, err
	}
	if receipts == nil {
		receipts = []receiptmodel.Fact{}
	}
	return receipts, nil
}
