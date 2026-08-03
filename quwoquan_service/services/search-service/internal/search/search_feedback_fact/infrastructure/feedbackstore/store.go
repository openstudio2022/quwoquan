package feedbackstore

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	feedbackapplication "quwoquan_service/services/search-service/internal/search/search_feedback_fact/application"
)

const (
	feedbackCollection         = "search_feedback_events"
	receiptsCollection         = "search_feedback_command_receipts"
	signalDeliveriesCollection = "search_feedback_signal_deliveries"

	FeedbackTTLSeconds = 7776000
)

type Store struct {
	feedback         *mongo.Collection
	receipts         *mongo.Collection
	signalDeliveries *mongo.Collection
}

var _ feedbackapplication.Sink = (*Store)(nil)
var _ feedbackapplication.HeatReader = (*Store)(nil)

func NewStore(db *mongo.Database) *Store {
	return &Store{
		feedback:         db.Collection(feedbackCollection),
		receipts:         db.Collection(receiptsCollection),
		signalDeliveries: db.Collection(signalDeliveriesCollection),
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
	if err := dropIndexIfExists(
		ctx,
		s.feedback,
		"idx_search_feedback_pending_signal",
	); err != nil {
		return fmt.Errorf("drop retired feedback signal index: %w", err)
	}
	if _, err := s.feedback.UpdateMany(
		ctx,
		bson.M{"$or": []bson.M{
			{"idempotencyKey": bson.M{"$exists": true}},
			{"signalPublishedAt": bson.M{"$exists": true}},
		}},
		bson.M{"$unset": bson.M{
			"idempotencyKey":    "",
			"signalPublishedAt": "",
		}},
	); err != nil {
		return fmt.Errorf("remove retired feedback fields: %w", err)
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
	signalDeliveryIndexes := []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "status", Value: 1},
				{Key: "leaseExpiresAt", Value: 1},
				{Key: "createdAt", Value: 1},
			},
			Options: options.Index().
				SetName("idx_search_feedback_signal_delivery_pending"),
		},
		{
			Keys: bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().
				SetName("idx_search_feedback_signal_delivery_expiry").
				SetExpireAfterSeconds(0),
		},
	}
	if _, err := s.feedback.Indexes().CreateMany(ctx, feedbackIndexes); err != nil {
		return fmt.Errorf("ensure search feedback indexes: %w", err)
	}
	if _, err := s.receipts.Indexes().CreateMany(ctx, receiptIndexes); err != nil {
		return fmt.Errorf("ensure search feedback receipt indexes: %w", err)
	}
	if _, err := s.signalDeliveries.Indexes().CreateMany(
		ctx,
		signalDeliveryIndexes,
	); err != nil {
		return fmt.Errorf("ensure search feedback signal delivery indexes: %w", err)
	}
	return nil
}

// DeleteClosedSubjects is SearchFeedbackFact's account-closure port. It owns
// facts, idempotency receipts, and pending signal deliveries as one privacy
// boundary; callers never receive collection handles.
func (s *Store) DeleteClosedSubjects(
	ctx context.Context,
	subjects []string,
	requestIDs []string,
) (int64, int64, int64, error) {
	clauses := bson.A{bson.M{"viewerId": bson.M{"$in": subjects}}}
	if len(requestIDs) > 0 {
		clauses = append(
			clauses,
			bson.M{"searchRequestId": bson.M{"$in": requestIDs}},
		)
	}
	filter := bson.M{"$or": clauses}
	cursor, err := s.feedback.Find(
		ctx,
		filter,
		options.Find().SetProjection(bson.M{"_id": 1}),
	)
	if err != nil {
		return 0, 0, 0, fmt.Errorf("scan closed-account search feedback: %w", err)
	}
	var rows []struct {
		ID bson.ObjectID `bson:"_id"`
	}
	if err := cursor.All(ctx, &rows); err != nil {
		_ = cursor.Close(ctx)
		return 0, 0, 0, fmt.Errorf("decode closed-account search feedback: %w", err)
	}
	if err := cursor.Close(ctx); err != nil {
		return 0, 0, 0, fmt.Errorf("close search feedback cursor: %w", err)
	}
	factIDs := make([]bson.ObjectID, 0, len(rows))
	for _, row := range rows {
		factIDs = append(factIDs, row.ID)
	}
	var deletedDeliveries int64
	if len(factIDs) > 0 {
		deliveryResult, deleteErr := s.signalDeliveries.DeleteMany(
			ctx,
			bson.M{"feedbackFactId": bson.M{"$in": factIDs}},
		)
		if deleteErr != nil {
			return 0, 0, 0, fmt.Errorf(
				"delete closed-account search feedback deliveries: %w",
				deleteErr,
			)
		}
		deletedDeliveries = deliveryResult.DeletedCount
	}
	receiptResult, err := s.receipts.DeleteMany(ctx, filter)
	if err != nil {
		return 0, 0, 0, fmt.Errorf("delete closed-account search feedback receipts: %w", err)
	}
	factResult, err := s.feedback.DeleteMany(ctx, filter)
	if err != nil {
		return 0, 0, 0, fmt.Errorf("delete closed-account search feedback: %w", err)
	}
	return factResult.DeletedCount, receiptResult.DeletedCount, deletedDeliveries, nil
}

func (s *Store) ListHeatFeedback(
	ctx context.Context,
	since time.Time,
	limit int64,
) ([]feedbackapplication.HeatFeedback, error) {
	if limit <= 0 {
		return []feedbackapplication.HeatFeedback{}, nil
	}
	cursor, err := s.feedback.Find(
		ctx,
		bson.M{"createdAt": bson.M{"$gte": since.UTC()}},
		options.Find().
			SetSort(bson.D{{Key: "createdAt", Value: -1}}).
			SetLimit(limit).
			SetProjection(bson.M{
				"searchRequestId": 1,
				"eventType":       1,
				"objectId":        1,
				"createdAt":       1,
			}),
	)
	if err != nil {
		return nil, fmt.Errorf("list SearchFeedbackFact heat source: %w", err)
	}
	defer cursor.Close(ctx)
	rows := make([]feedbackapplication.HeatFeedback, 0, 256)
	for cursor.Next(ctx) {
		var row struct {
			SearchRequestID string    `bson:"searchRequestId"`
			EventType       string    `bson:"eventType"`
			ObjectID        string    `bson:"objectId"`
			CreatedAt       time.Time `bson:"createdAt"`
		}
		if err := cursor.Decode(&row); err != nil {
			return nil, fmt.Errorf("decode SearchFeedbackFact heat source: %w", err)
		}
		rows = append(rows, feedbackapplication.HeatFeedback{
			SearchRequestID: row.SearchRequestID,
			EventType:       row.EventType,
			ObjectID:        row.ObjectID,
			CreatedAt:       row.CreatedAt,
		})
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("scan SearchFeedbackFact heat source: %w", err)
	}
	return rows, nil
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
	ID              bson.ObjectID `bson:"_id,omitempty"`
	SearchRequestID string        `bson:"searchRequestId"`
	ViewerID        string        `bson:"viewerId,omitempty"`
	CommandDigest   string        `bson:"commandDigest"`
	EventType       string        `bson:"eventType"`
	ObjectID        string        `bson:"objectId,omitempty"`
	Target          string        `bson:"target,omitempty"`
	RankPosition    int           `bson:"rankPosition,omitempty"`
	ReferralSource  string        `bson:"referralSource,omitempty"`
	FeedRequestID   string        `bson:"feedRequestId,omitempty"`
	DwellMs         int           `bson:"dwellMs,omitempty"`
	CreatedAt       time.Time     `bson:"createdAt"`
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

// feedbackSignalDeliveryDoc is the mutable delivery state for one stable
// recommendation signal. The associated feedbackDoc remains append-only.
type feedbackSignalDeliveryDoc struct {
	ID                string        `bson:"_id"`
	FeedbackFactID    bson.ObjectID `bson:"feedbackFactId"`
	SignalPayloadJSON string        `bson:"signalPayloadJson"`
	Status            string        `bson:"status"`
	LeaseOwner        string        `bson:"leaseOwner,omitempty"`
	LeaseExpiresAt    *time.Time    `bson:"leaseExpiresAt,omitempty"`
	LastAttemptAt     *time.Time    `bson:"lastAttemptAt,omitempty"`
	PublishedAt       *time.Time    `bson:"publishedAt,omitempty"`
	CreatedAt         time.Time     `bson:"createdAt"`
	UpdatedAt         time.Time     `bson:"updatedAt"`
	ExpiresAt         *time.Time    `bson:"expiresAt,omitempty"`
}

const (
	receiptApplying  = "applying"
	receiptCompleted = "completed"
	receiptConflict  = "conflict"

	signalDeliveryPending    = "pending"
	signalDeliveryPublishing = "publishing"
	signalDeliveryPublished  = "published"
)

func (s *Store) Record(
	ctx context.Context,
	event feedbackapplication.Event,
	meta feedbackapplication.CommandMeta,
) error {
	session, err := s.feedback.Database().Client().StartSession()
	if err != nil {
		return err
	}
	defer session.EndSession(ctx)

	semanticConflict := false
	_, err = session.WithTransaction(
		ctx,
		func(txCtx context.Context) (any, error) {
			receipt, receiptErr := s.claimReceipt(txCtx, event, meta)
			if receiptErr != nil {
				return nil, receiptErr
			}
			if receipt.Status == receiptCompleted {
				return nil, nil
			}

			document, conflict, documentErr := s.ensureFeedbackFact(
				txCtx,
				event,
				meta,
			)
			if documentErr != nil {
				return nil, documentErr
			}
			if conflict {
				if markErr := s.markReceipt(
					txCtx,
					meta.IdempotencyKey,
					receiptConflict,
				); markErr != nil {
					return nil, markErr
				}
				semanticConflict = true
				return nil, nil
			}
			if deliveryErr := s.ensureSignalDelivery(txCtx, document); deliveryErr != nil {
				return nil, deliveryErr
			}
			if markErr := s.markReceipt(
				txCtx,
				meta.IdempotencyKey,
				receiptCompleted,
			); markErr != nil {
				return nil, markErr
			}
			return nil, nil
		},
	)
	if err != nil {
		return err
	}
	if semanticConflict {
		return feedbackapplication.ErrIdempotencyConflict
	}
	return nil
}

func (s *Store) ensureFeedbackFact(
	ctx context.Context,
	event feedbackapplication.Event,
	meta feedbackapplication.CommandMeta,
) (feedbackDoc, bool, error) {
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
	var existing feedbackDoc
	if err := s.feedback.FindOneAndUpdate(
		ctx,
		bson.M{
			"searchRequestId": event.SearchRequestID,
			"eventType":       event.EventType,
			"objectId":        event.ObjectID,
		},
		bson.M{"$setOnInsert": document},
		options.FindOneAndUpdate().
			SetUpsert(true).
			SetReturnDocument(options.After),
	).Decode(&existing); err != nil {
		return feedbackDoc{}, false, fmt.Errorf("upsert search feedback fact: %w", err)
	}
	if existing.CommandDigest != meta.CommandDigest ||
		existing.ViewerID != event.ViewerID {
		return feedbackDoc{}, true, nil
	}
	return existing, false, nil
}

func (s *Store) ensureSignalDelivery(
	ctx context.Context,
	document feedbackDoc,
) error {
	signal, ok := feedbackapplication.RecommendationSignal(
		feedbackapplication.Event{
			SearchRequestID: document.SearchRequestID,
			ViewerID:        document.ViewerID,
			EventType:       document.EventType,
			ObjectID:        document.ObjectID,
			Target:          document.Target,
			RankPosition:    document.RankPosition,
			ReferralSource:  document.ReferralSource,
			FeedRequestID:   document.FeedRequestID,
			DwellMs:         document.DwellMs,
		},
		document.CreatedAt,
	)
	if !ok {
		if document.EventType == "click" {
			return fmt.Errorf(
				"committed click feedback cannot produce recommendation signal",
			)
		}
		return nil
	}
	payload, err := json.Marshal(signal)
	if err != nil {
		return fmt.Errorf("serialize feedback recommendation signal: %w", err)
	}
	now := time.Now().UTC()
	delivery := feedbackSignalDeliveryDoc{
		ID:                signal.SignalID,
		FeedbackFactID:    document.ID,
		SignalPayloadJSON: string(payload),
		Status:            signalDeliveryPending,
		CreatedAt:         now,
		UpdatedAt:         now,
	}
	var existing feedbackSignalDeliveryDoc
	if err := s.signalDeliveries.FindOneAndUpdate(
		ctx,
		bson.M{"_id": signal.SignalID},
		bson.M{"$setOnInsert": delivery},
		options.FindOneAndUpdate().
			SetUpsert(true).
			SetReturnDocument(options.After),
	).Decode(&existing); err != nil {
		return fmt.Errorf("upsert search feedback signal delivery: %w", err)
	}
	if existing.FeedbackFactID != document.ID ||
		existing.SignalPayloadJSON != delivery.SignalPayloadJSON {
		return fmt.Errorf(
			"feedback signal delivery invariant conflict for %s",
			signal.SignalID,
		)
	}
	return nil
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
	if err := s.receipts.FindOneAndUpdate(
		ctx,
		bson.M{"_id": meta.IdempotencyKey},
		bson.M{"$setOnInsert": receipt},
		options.FindOneAndUpdate().
			SetUpsert(true).
			SetReturnDocument(options.After),
	).Decode(&receipt); err != nil {
		return feedbackCommandReceiptDoc{},
			fmt.Errorf("upsert search feedback receipt: %w", err)
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

func (s *Store) leaseNextSignalDelivery(
	ctx context.Context,
	leaseOwner string,
	leaseDuration time.Duration,
) (feedbackSignalDeliveryDoc, bool, error) {
	now := time.Now().UTC()
	leaseExpiresAt := now.Add(leaseDuration)
	var delivery feedbackSignalDeliveryDoc
	err := s.signalDeliveries.FindOneAndUpdate(
		ctx,
		bson.M{
			"$or": []bson.M{
				{"status": signalDeliveryPending},
				{
					"status":         signalDeliveryPublishing,
					"leaseExpiresAt": bson.M{"$lte": now},
				},
			},
		},
		bson.M{"$set": bson.M{
			"status":         signalDeliveryPublishing,
			"leaseOwner":     leaseOwner,
			"leaseExpiresAt": leaseExpiresAt,
			"lastAttemptAt":  now,
			"updatedAt":      now,
		}},
		options.FindOneAndUpdate().
			SetSort(bson.D{
				{Key: "createdAt", Value: 1},
				{Key: "_id", Value: 1},
			}).
			SetReturnDocument(options.After),
	).Decode(&delivery)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return feedbackSignalDeliveryDoc{}, false, nil
	}
	if err != nil {
		return feedbackSignalDeliveryDoc{}, false, err
	}
	return delivery, true, nil
}

func (s *Store) acknowledgeSignalDelivery(
	ctx context.Context,
	deliveryID string,
	leaseOwner string,
) (bool, error) {
	now := time.Now().UTC()
	expiresAt := now.Add(time.Duration(FeedbackTTLSeconds) * time.Second)
	result, err := s.signalDeliveries.UpdateOne(
		ctx,
		bson.M{
			"_id":        deliveryID,
			"status":     signalDeliveryPublishing,
			"leaseOwner": leaseOwner,
		},
		bson.M{
			"$set": bson.M{
				"status":      signalDeliveryPublished,
				"publishedAt": now,
				"updatedAt":   now,
				"expiresAt":   expiresAt,
			},
			"$unset": bson.M{
				"leaseOwner":     "",
				"leaseExpiresAt": "",
			},
		},
	)
	if err != nil {
		return false, err
	}
	return result.MatchedCount == 1, nil
}

func (s *Store) releaseSignalDelivery(
	ctx context.Context,
	deliveryID string,
	leaseOwner string,
) error {
	now := time.Now().UTC()
	_, err := s.signalDeliveries.UpdateOne(
		ctx,
		bson.M{
			"_id":        deliveryID,
			"status":     signalDeliveryPublishing,
			"leaseOwner": leaseOwner,
		},
		bson.M{
			"$set": bson.M{
				"status":    signalDeliveryPending,
				"updatedAt": now,
			},
			"$unset": bson.M{
				"leaseOwner":     "",
				"leaseExpiresAt": "",
			},
		},
	)
	return err
}
