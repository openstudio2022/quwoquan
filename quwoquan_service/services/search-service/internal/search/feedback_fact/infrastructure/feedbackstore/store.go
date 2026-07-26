package feedbackstore

import (
	"context"
	"errors"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	feedbackapplication "quwoquan_service/services/search-service/internal/search/feedback_fact/application"
)

const (
	feedbackCollection = "search_feedback_events"
	receiptsCollection = "search_feedback_command_receipts"

	FeedbackTTLSeconds = 7776000
)

type Store struct {
	feedback *mongo.Collection
	receipts *mongo.Collection
}

var _ feedbackapplication.Sink = (*Store)(nil)

func NewStore(db *mongo.Database) *Store {
	return &Store{
		feedback: db.Collection(feedbackCollection),
		receipts: db.Collection(receiptsCollection),
	}
}

func (s *Store) EnsureIndexes(ctx context.Context) error {
	if err := dropIndexIfExists(
		ctx,
		s.feedback,
		"uq_search_feedback_idempotency",
	); err != nil {
		return fmt.Errorf("drop retired feedback idempotency index: %w", err)
	}
	if _, err := s.feedback.UpdateMany(
		ctx,
		bson.M{"idempotencyKey": bson.M{"$exists": true}},
		bson.M{"$unset": bson.M{"idempotencyKey": ""}},
	); err != nil {
		return fmt.Errorf("remove retired feedback idempotency field: %w", err)
	}
	feedbackIndexes := []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "searchRequestId", Value: 1},
				{Key: "createdAt", Value: -1},
			},
			Options: options.Index().SetName("idx_search_feedback_request"),
		},
		{
			Keys: bson.D{
				{Key: "viewerId", Value: 1},
				{Key: "createdAt", Value: -1},
			},
			Options: options.Index().SetName("idx_search_feedback_viewer_created"),
		},
		{
			Keys: bson.D{
				{Key: "objectId", Value: 1},
				{Key: "eventType", Value: 1},
				{Key: "createdAt", Value: -1},
			},
			Options: options.Index().SetName("idx_search_feedback_object"),
		},
		{
			Keys: bson.D{
				{Key: "searchRequestId", Value: 1},
				{Key: "eventType", Value: 1},
				{Key: "objectId", Value: 1},
			},
			Options: options.Index().
				SetUnique(true).
				SetName("uq_search_feedback_dedupe"),
		},
		{
			Keys: bson.D{{Key: "createdAt", Value: 1}},
			Options: options.Index().
				SetName("idx_search_feedback_ttl").
				SetExpireAfterSeconds(int32(FeedbackTTLSeconds)),
		},
	}
	receiptIndexes := []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "viewerId", Value: 1},
				{Key: "createdAt", Value: -1},
			},
			Options: options.Index().
				SetName("idx_search_feedback_receipt_viewer_created"),
		},
		{
			Keys: bson.D{{Key: "searchRequestId", Value: 1}},
			Options: options.Index().
				SetName("idx_search_feedback_receipt_request"),
		},
		{
			Keys: bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().
				SetName("idx_search_feedback_receipt_expiry").
				SetExpireAfterSeconds(0),
		},
	}
	if _, err := s.feedback.Indexes().CreateMany(ctx, feedbackIndexes); err != nil {
		return fmt.Errorf("ensure search feedback indexes: %w", err)
	}
	if _, err := s.receipts.Indexes().CreateMany(ctx, receiptIndexes); err != nil {
		return fmt.Errorf("ensure search feedback receipt indexes: %w", err)
	}
	return nil
}

func dropIndexIfExists(
	ctx context.Context,
	collection *mongo.Collection,
	name string,
) error {
	if collection == nil {
		return errors.New("collection is nil")
	}
	if err := collection.Indexes().DropOne(ctx, name); err != nil {
		var commandError mongo.CommandError
		if errors.As(err, &commandError) &&
			(commandError.Code == 26 || commandError.Code == 27) {
			return nil
		}
		return err
	}
	return nil
}

type feedbackDoc struct {
	SearchRequestID string    `bson:"searchRequestId"`
	ViewerID        string    `bson:"viewerId,omitempty"`
	CommandDigest   string    `bson:"commandDigest"`
	EventType       string    `bson:"eventType"`
	ObjectID        string    `bson:"objectId,omitempty"`
	Target          string    `bson:"target,omitempty"`
	RankPosition    int       `bson:"rankPosition,omitempty"`
	ReferralSource  string    `bson:"referralSource,omitempty"`
	FeedRequestID   string    `bson:"feedRequestId,omitempty"`
	DwellMs         int       `bson:"dwellMs,omitempty"`
	CreatedAt       time.Time `bson:"createdAt"`
}

type feedbackCommandReceiptDoc struct {
	ID              string    `bson:"_id"`
	CommandDigest   string    `bson:"commandDigest"`
	ViewerID        string    `bson:"viewerId,omitempty"`
	SearchRequestID string    `bson:"searchRequestId"`
	EventType       string    `bson:"eventType"`
	ObjectID        string    `bson:"objectId,omitempty"`
	Status          string    `bson:"status"`
	CreatedAt       time.Time `bson:"createdAt"`
	UpdatedAt       time.Time `bson:"updatedAt"`
	ExpiresAt       time.Time `bson:"expiresAt"`
}

const (
	receiptApplying  = "applying"
	receiptCompleted = "completed"
	receiptConflict  = "conflict"
)

func (s *Store) Record(
	ctx context.Context,
	event feedbackapplication.Event,
	meta feedbackapplication.CommandMeta,
) error {
	receipt, err := s.claimReceipt(ctx, event, meta)
	if err != nil {
		return err
	}
	if receipt.Status == receiptCompleted {
		return nil
	}
	document := feedbackDoc{
		SearchRequestID: event.SearchRequestID,
		ViewerID:        event.ViewerID,
		CommandDigest:   meta.CommandDigest,
		EventType:       event.EventType,
		ObjectID:        event.ObjectID,
		Target:          event.Target,
		RankPosition:    event.RankPosition,
		ReferralSource:  event.ReferralSource,
		FeedRequestID:   event.FeedRequestID,
		DwellMs:         event.DwellMs,
		CreatedAt:       time.Now().UTC(),
	}
	_, err = s.feedback.InsertOne(ctx, document)
	if err != nil && !mongo.IsDuplicateKeyError(err) {
		return err
	}
	if mongo.IsDuplicateKeyError(err) {
		var existing feedbackDoc
		if findErr := s.feedback.FindOne(ctx, bson.M{
			"searchRequestId": event.SearchRequestID,
			"eventType":       event.EventType,
			"objectId":        event.ObjectID,
		}).Decode(&existing); findErr != nil {
			return findErr
		}
		if existing.CommandDigest != meta.CommandDigest ||
			existing.ViewerID != event.ViewerID {
			if markErr := s.markReceipt(
				ctx,
				meta.IdempotencyKey,
				receiptConflict,
			); markErr != nil {
				return markErr
			}
			return feedbackapplication.ErrIdempotencyConflict
		}
	}
	return s.markReceipt(ctx, meta.IdempotencyKey, receiptCompleted)
}

func (s *Store) claimReceipt(
	ctx context.Context,
	event feedbackapplication.Event,
	meta feedbackapplication.CommandMeta,
) (feedbackCommandReceiptDoc, error) {
	now := time.Now().UTC()
	receipt := feedbackCommandReceiptDoc{
		ID:              meta.IdempotencyKey,
		CommandDigest:   meta.CommandDigest,
		ViewerID:        event.ViewerID,
		SearchRequestID: event.SearchRequestID,
		EventType:       event.EventType,
		ObjectID:        event.ObjectID,
		Status:          receiptApplying,
		CreatedAt:       now,
		UpdatedAt:       now,
		ExpiresAt: now.Add(
			time.Duration(FeedbackTTLSeconds) * time.Second,
		),
	}
	if _, err := s.receipts.InsertOne(ctx, receipt); err == nil {
		return receipt, nil
	} else if !mongo.IsDuplicateKeyError(err) {
		return feedbackCommandReceiptDoc{}, err
	}
	if err := s.receipts.FindOne(
		ctx,
		bson.M{"_id": meta.IdempotencyKey},
	).Decode(&receipt); err != nil {
		return feedbackCommandReceiptDoc{}, err
	}
	if receipt.CommandDigest != meta.CommandDigest ||
		receipt.ViewerID != event.ViewerID ||
		receipt.SearchRequestID != event.SearchRequestID ||
		receipt.EventType != event.EventType ||
		receipt.ObjectID != event.ObjectID ||
		receipt.Status == receiptConflict {
		return feedbackCommandReceiptDoc{},
			feedbackapplication.ErrIdempotencyConflict
	}
	if receipt.Status != receiptApplying &&
		receipt.Status != receiptCompleted {
		return feedbackCommandReceiptDoc{},
			fmt.Errorf("unsupported search feedback receipt status %q", receipt.Status)
	}
	return receipt, nil
}

func (s *Store) markReceipt(
	ctx context.Context,
	idempotencyKey string,
	status string,
) error {
	result, err := s.receipts.UpdateOne(
		ctx,
		bson.M{"_id": idempotencyKey},
		bson.M{"$set": bson.M{
			"status":    status,
			"updatedAt": time.Now().UTC(),
		}},
	)
	if err != nil {
		return fmt.Errorf("mark search feedback receipt %s: %w", status, err)
	}
	if result.MatchedCount != 1 {
		return fmt.Errorf("mark search feedback receipt %s: receipt missing", status)
	}
	return nil
}
