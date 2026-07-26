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

	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/domain/model"
)

var _ application.CallStore = (*MongoCallStore)(nil)

// MongoCallStore 以三 collection（state / command_receipts / outbox）单事务
// 提供 CallSession 聚合的原子提交：version CAS、幂等 receipt 与同库 outbox。
type MongoCallStore struct {
	calls    *mongo.Collection
	receipts *mongo.Collection
	outbox   *mongo.Collection
}

func NewMongoCallStore(db *mongo.Database) *MongoCallStore {
	return &MongoCallStore{
		calls:    db.Collection("call_sessions"),
		receipts: db.Collection("call_session_command_receipts"),
		outbox:   db.Collection("call_session_outbox"),
	}
}

func (s *MongoCallStore) EnsureIndexes(ctx context.Context) error {
	if _, err := s.calls.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "initiatorId", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_cs_initiator_created"),
		},
		{
			Keys: bson.D{
				{Key: "status", Value: 1},
				{Key: "maxParticipants", Value: 1},
				{Key: "createdAt", Value: 1},
			},
			Options: options.Index().SetName("idx_cs_status"),
		},
		{
			Keys:    bson.D{{Key: "conversationId", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_cs_conv_created").SetSparse(true),
		},
		{
			Keys:    bson.D{{Key: "circleId", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_cs_circle_created").SetSparse(true),
		},
		{
			Keys:    bson.D{{Key: "roomId", Value: 1}},
			Options: options.Index().SetName("idx_cs_room").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "participants.userId", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_cs_participant_user"),
		},
		{
			Keys: bson.D{
				{Key: "participants.userId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "createdAt", Value: 1},
			},
			Options: options.Index().SetName("idx_cs_active_participant"),
		},
		{
			Keys: bson.D{
				{Key: "status", Value: 1},
				{Key: "endReason", Value: 1},
				{Key: "createdAt", Value: -1},
			},
			Options: options.Index().SetName("idx_cs_ended_reason"),
		},
		{
			Keys:    bson.D{{Key: "_id", Value: 1}, {Key: "version", Value: 1}},
			Options: options.Index().SetName("idx_cs_version").SetUnique(true),
		},
	}); err != nil {
		return fmt.Errorf("ensure call session indexes: %w", err)
	}
	if _, err := s.receipts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "aggregateId", Value: 1},
				{Key: "aggregateVersion", Value: -1},
			},
			Options: options.Index().SetName("idx_cs_receipts_aggregate"),
		},
		{
			Keys:    bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().SetName("idx_cs_receipts_expire").SetExpireAfterSeconds(0),
		},
	}); err != nil {
		return fmt.Errorf("ensure call command receipt indexes: %w", err)
	}
	if _, err := s.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "occurredAt", Value: 1},
				{Key: "_id", Value: 1},
			},
			Options: options.Index().SetName("idx_cs_outbox_replay"),
		},
		{
			Keys: bson.D{
				{Key: "aggregateId", Value: 1},
				{Key: "aggregateVersion", Value: 1},
				{Key: "eventType", Value: 1},
				{Key: "deliveryKey", Value: 1},
			},
			Options: options.Index().SetName("idx_cs_outbox_aggregate_version"),
		},
	}); err != nil {
		return fmt.Errorf("ensure call outbox indexes: %w", err)
	}
	return nil
}

type callCommandReceiptDocument struct {
	ID          string             `bson:"_id"`
	AggregateID string             `bson:"aggregateId"`
	Command     string             `bson:"commandName"`
	Digest      string             `bson:"commandDigest"`
	Version     int64              `bson:"aggregateVersion"`
	Result      *model.CallSession `bson:"result"`
	CreatedAt   time.Time          `bson:"createdAt"`
	ExpiresAt   time.Time          `bson:"expiresAt"`
}

type callOutboxDocument struct {
	ID               string     `bson:"_id"`
	EventType        string     `bson:"eventType"`
	AggregateID      string     `bson:"aggregateId"`
	AggregateVersion int64      `bson:"aggregateVersion"`
	DeliveryKey      string     `bson:"deliveryKey,omitempty"`
	Payload          []byte     `bson:"payload"`
	OccurredAt       time.Time  `bson:"occurredAt"`
	PublishedAt      *time.Time `bson:"publishedAt,omitempty"`
}

func (s *MongoCallStore) CreateCall(ctx context.Context, session *model.CallSession) error {
	if session.Version == 0 {
		session.Version = 1
	}
	_, err := s.calls.InsertOne(ctx, session)
	return err
}

func (s *MongoCallStore) FindCallByID(ctx context.Context, id string) (*model.CallSession, error) {
	var session model.CallSession
	err := s.calls.FindOne(ctx, bson.M{"_id": id}).Decode(&session)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &session, nil
}

func (s *MongoCallStore) FindActiveCallForUser(ctx context.Context, userID string) (*model.CallSession, error) {
	var session model.CallSession
	err := s.calls.FindOne(
		ctx,
		bson.M{
			"participants.userId": userID,
			"status":              bson.M{"$nin": []string{model.StatusEnded}},
		},
		options.FindOne().SetSort(bson.D{{Key: "createdAt", Value: -1}}),
	).Decode(&session)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &session, nil
}

func (s *MongoCallStore) FindActiveCallsForUsers(
	ctx context.Context,
	userIDs []string,
	limit int,
) ([]*model.CallSession, error) {
	normalizedIDs := make([]string, 0, len(userIDs))
	seen := make(map[string]struct{}, len(userIDs))
	for _, userID := range userIDs {
		userID = strings.TrimSpace(userID)
		if userID == "" {
			continue
		}
		if _, duplicate := seen[userID]; duplicate {
			continue
		}
		seen[userID] = struct{}{}
		normalizedIDs = append(normalizedIDs, userID)
	}
	if len(normalizedIDs) == 0 {
		return []*model.CallSession{}, nil
	}
	if limit <= 0 {
		limit = 100
	}
	cursor, err := s.calls.Find(
		ctx,
		bson.M{
			"participants.userId": bson.M{"$in": normalizedIDs},
			"status":              bson.M{"$ne": model.StatusEnded},
		},
		options.Find().
			SetSort(bson.D{{Key: "createdAt", Value: 1}, {Key: "_id", Value: 1}}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var sessions []*model.CallSession
	if err := cursor.All(ctx, &sessions); err != nil {
		return nil, err
	}
	return sessions, nil
}

// FindOverdueRingingCalls 用 idx_cs_status 按 1v1/群聊阈值筛出到期候选。
func (s *MongoCallStore) FindOverdueRingingCalls(
	ctx context.Context,
	oneToOneCutoff time.Time,
	groupCutoff time.Time,
	limit int,
) ([]*model.CallSession, error) {
	if limit <= 0 {
		limit = 100
	}
	cur, err := s.calls.Find(
		ctx,
		bson.M{
			"status": bson.M{"$in": []string{model.StatusInitiated, model.StatusRinging}},
			"$or": bson.A{
				bson.M{
					"maxParticipants": bson.M{"$lte": model.MaxParticipants1v1},
					"createdAt":       bson.M{"$lte": oneToOneCutoff.UTC()},
				},
				bson.M{
					"maxParticipants": bson.M{"$gt": model.MaxParticipants1v1},
					"createdAt":       bson.M{"$lte": groupCutoff.UTC()},
				},
			},
		},
		options.Find().SetSort(bson.D{{Key: "createdAt", Value: 1}}).SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, err
	}
	defer cur.Close(ctx)
	var sessions []*model.CallSession
	if err := cur.All(ctx, &sessions); err != nil {
		return nil, err
	}
	return sessions, nil
}

func (s *MongoCallStore) FindReceipt(
	ctx context.Context,
	idempotencyKey, commandName, commandDigest string,
) (application.CallCommitResult, bool, error) {
	receipt, found, err := s.loadReceipt(ctx, idempotencyKey)
	if err != nil || !found {
		return application.CallCommitResult{}, found, err
	}
	if !receipt.ExpiresAt.After(time.Now().UTC()) {
		_, _ = s.receipts.DeleteOne(ctx, bson.M{"_id": receipt.ID})
		return application.CallCommitResult{}, false, nil
	}
	if receipt.Command != commandName || receipt.Digest != commandDigest {
		return application.CallCommitResult{}, false, application.ErrVersionConflict
	}
	return application.CallCommitResult{Session: receipt.Result, Replayed: true}, true, nil
}

func (s *MongoCallStore) RecordNoopReceipt(
	ctx context.Context,
	noop application.CallNoopReceipt,
) (application.CallCommitResult, error) {
	if replayed, found, err := s.FindReceipt(ctx, noop.IdempotencyKey, noop.CommandName, noop.CommandDigest); err != nil || found {
		return replayed, err
	}
	doc := callCommandReceiptDocument{
		ID:          noop.IdempotencyKey,
		AggregateID: noop.Session.ID,
		Command:     noop.CommandName,
		Digest:      noop.CommandDigest,
		Version:     noop.Session.Version,
		Result:      noop.Session,
		CreatedAt:   time.Now().UTC(),
		ExpiresAt:   noopExpiry(noop.ReceiptExpiresAt),
	}
	if _, err := s.receipts.InsertOne(ctx, doc); err != nil {
		if mongo.IsDuplicateKeyError(err) {
			replayed, found, findErr := s.FindReceipt(ctx, noop.IdempotencyKey, noop.CommandName, noop.CommandDigest)
			if findErr == nil && found {
				return replayed, nil
			}
			return application.CallCommitResult{}, findErr
		}
		return application.CallCommitResult{}, err
	}
	return application.CallCommitResult{Session: noop.Session}, nil
}

func (s *MongoCallStore) Commit(
	ctx context.Context,
	commit application.CallCommit,
) (application.CallCommitResult, error) {
	session := commit.Session
	session.Version = commit.ExpectedVersion + 1
	session.UpdatedAt = time.Now().UTC()

	sessionClient := s.calls.Database().Client()
	mongoSession, err := sessionClient.StartSession()
	if err != nil {
		return application.CallCommitResult{}, err
	}
	defer mongoSession.EndSession(ctx)

	var result application.CallCommitResult
	_, err = mongoSession.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if receipt, found, receiptErr := s.loadReceipt(txCtx, commit.IdempotencyKey); receiptErr != nil {
			return nil, receiptErr
		} else if found && receipt.ExpiresAt.After(time.Now().UTC()) {
			if receipt.Command != commit.CommandName || receipt.Digest != commit.CommandDigest {
				return nil, application.ErrVersionConflict
			}
			result = application.CallCommitResult{Session: receipt.Result, Replayed: true}
			return nil, nil
		}

		if commit.ExpectedVersion == 0 {
			if _, err := s.calls.InsertOne(txCtx, session); err != nil {
				return nil, err
			}
		} else {
			replaced, err := s.calls.ReplaceOne(
				txCtx,
				bson.M{"_id": session.ID, "version": commit.ExpectedVersion},
				session,
			)
			if err != nil {
				return nil, err
			}
			if replaced.MatchedCount != 1 {
				return nil, application.ErrVersionConflict
			}
		}

		for _, evt := range commit.Events {
			if _, err := s.outbox.InsertOne(txCtx, callOutboxDocument{
				ID:               evt.EventID,
				EventType:        evt.EventType,
				AggregateID:      evt.AggregateID,
				AggregateVersion: session.Version,
				DeliveryKey:      evt.DeliveryKey,
				Payload:          append([]byte(nil), evt.Payload...),
				OccurredAt:       evt.OccurredAt.UTC(),
			}); err != nil {
				return nil, err
			}
		}

		if _, err := s.receipts.InsertOne(txCtx, callCommandReceiptDocument{
			ID:          commit.IdempotencyKey,
			AggregateID: session.ID,
			Command:     commit.CommandName,
			Digest:      commit.CommandDigest,
			Version:     session.Version,
			Result:      session,
			CreatedAt:   time.Now().UTC(),
			ExpiresAt:   noopExpiry(commit.ReceiptExpiresAt),
		}); err != nil {
			return nil, err
		}
		result = application.CallCommitResult{Session: session}
		return nil, nil
	})
	if err != nil {
		return application.CallCommitResult{}, err
	}
	return result, nil
}

func (s *MongoCallStore) loadReceipt(
	ctx context.Context,
	idempotencyKey string,
) (callCommandReceiptDocument, bool, error) {
	var receipt callCommandReceiptDocument
	err := s.receipts.FindOne(ctx, bson.M{"_id": idempotencyKey}).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return callCommandReceiptDocument{}, false, nil
	}
	if err != nil {
		return callCommandReceiptDocument{}, false, err
	}
	return receipt, true, nil
}

func (s *MongoCallStore) ReadPendingOutbox(
	ctx context.Context,
	limit int,
) ([]application.CallOutboxEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	cursor, err := s.outbox.Find(
		ctx,
		bson.M{"publishedAt": bson.M{"$exists": false}},
		options.Find().
			SetSort(bson.D{{Key: "occurredAt", Value: 1}, {Key: "_id", Value: 1}}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var documents []callOutboxDocument
	if err := cursor.All(ctx, &documents); err != nil {
		return nil, err
	}
	events := make([]application.CallOutboxEvent, 0, len(documents))
	for _, document := range documents {
		events = append(events, application.CallOutboxEvent{
			EventID:          document.ID,
			EventType:        document.EventType,
			AggregateID:      document.AggregateID,
			AggregateVersion: document.AggregateVersion,
			DeliveryKey:      document.DeliveryKey,
			Payload:          append([]byte(nil), document.Payload...),
			OccurredAt:       document.OccurredAt,
		})
	}
	return events, nil
}

func (s *MongoCallStore) MarkOutboxPublished(
	ctx context.Context,
	eventID string,
	publishedAt time.Time,
) error {
	result, err := s.outbox.UpdateOne(
		ctx,
		bson.M{"_id": eventID},
		bson.M{"$set": bson.M{"publishedAt": publishedAt.UTC()}},
	)
	if err != nil {
		return err
	}
	if result.MatchedCount != 1 {
		return fmt.Errorf("rtc call outbox event %s not found", eventID)
	}
	return nil
}

func (s *MongoCallStore) ListCallsByUserID(
	ctx context.Context,
	userID string,
	query application.CallHistoryQuery,
) (application.CallHistoryPage, error) {
	limit := query.Limit
	if limit <= 0 {
		limit = 20
	} else if limit > 100 {
		limit = 100
	}
	filter := bson.M{"participants.userId": userID}
	if query.Status != "" {
		filter["status"] = query.Status
	}
	if query.MissedOnly {
		if query.Status != "" && query.Status != model.StatusEnded {
			return application.CallHistoryPage{Items: []*model.CallSession{}}, nil
		}
		filter["status"] = model.StatusEnded
		filter["initiatorId"] = bson.M{"$ne": userID}
		filter["endReason"] = bson.M{"$in": []string{
			model.EndReasonNoAnswer,
			model.EndReasonTimeout,
			model.EndReasonCancelled,
		}}
	}
	if query.Cursor != "" {
		var anchor struct {
			ID        string    `bson:"_id"`
			CreatedAt time.Time `bson:"createdAt"`
		}
		err := s.calls.FindOne(
			ctx,
			bson.M{
				"_id":                 query.Cursor,
				"participants.userId": userID,
			},
			options.FindOne().SetProjection(bson.M{"_id": 1, "createdAt": 1}),
		).Decode(&anchor)
		if errors.Is(err, mongo.ErrNoDocuments) {
			return application.CallHistoryPage{Items: []*model.CallSession{}}, nil
		}
		if err != nil {
			return application.CallHistoryPage{}, err
		}
		filter["$or"] = bson.A{
			bson.M{"createdAt": bson.M{"$lt": anchor.CreatedAt}},
			bson.M{
				"createdAt": anchor.CreatedAt,
				"_id":       bson.M{"$lt": anchor.ID},
			},
		}
	}
	cur, err := s.calls.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{{Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}}).
			SetLimit(int64(limit+1)),
	)
	if err != nil {
		return application.CallHistoryPage{}, err
	}
	defer cur.Close(ctx)
	sessions := make([]*model.CallSession, 0, limit+1)
	if err := cur.All(ctx, &sessions); err != nil {
		return application.CallHistoryPage{}, err
	}
	page := application.CallHistoryPage{Items: sessions}
	if len(sessions) > limit {
		page.Items = sessions[:limit]
		page.NextCursor = page.Items[len(page.Items)-1].ID
	}
	return page, nil
}

func noopExpiry(candidate time.Time) time.Time {
	if candidate.IsZero() {
		return time.Now().UTC().Add(24 * time.Hour)
	}
	return candidate.UTC()
}
