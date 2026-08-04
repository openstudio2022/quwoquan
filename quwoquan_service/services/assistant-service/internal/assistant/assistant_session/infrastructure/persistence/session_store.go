package persistence

import (
	"context"
	"encoding/base64"
	"errors"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/model"
	sessionports "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
)

func encodeKeysetCursor(at time.Time, id string) string {
	return base64.RawURLEncoding.EncodeToString(
		[]byte(fmt.Sprintf("%d|%s", at.UTC().UnixNano(), id)),
	)
}

func decodeKeysetCursor(cursor string) (time.Time, string, bool) {
	raw, err := base64.RawURLEncoding.DecodeString(strings.TrimSpace(cursor))
	if err != nil {
		return time.Time{}, "", false
	}
	parts := strings.SplitN(string(raw), "|", 2)
	if len(parts) != 2 {
		return time.Time{}, "", false
	}
	var nanos int64
	if _, err := fmt.Sscanf(parts[0], "%d", &nanos); err != nil {
		return time.Time{}, "", false
	}
	return time.Unix(0, nanos).UTC(), parts[1], true
}

func clampPageLimit(limit int) int {
	if limit <= 0 {
		return 20
	}
	if limit > 50 {
		return 50
	}
	return limit
}

type MongoSessionStore struct {
	sessions *mongo.Collection
	receipts *mongo.Collection
}

func NewMongoSessionStore(db *mongo.Database) *MongoSessionStore {
	if db == nil {
		panic("assistant session database is required")
	}
	return &MongoSessionStore{
		sessions: db.Collection("assistant_sessions"),
		receipts: db.Collection("assistant_session_summary_receipts"),
	}
}

func (store *MongoSessionStore) EnsureIndexes(ctx context.Context) error {
	_, err := store.sessions.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "userId", Value: 1}, {Key: "updatedAt", Value: -1}},
			Options: options.Index().SetName("idx_sessions_user_updated"),
		},
		{
			Keys: bson.D{{Key: "userId", Value: 1}, {Key: "clientRequestId", Value: 1}},
			Options: options.Index().
				SetName("uq_sessions_client_request").
				SetUnique(true).
				SetPartialFilterExpression(bson.M{
					"clientRequestId": bson.M{"$type": "string"},
				}),
		},
	})
	if err != nil {
		return fmt.Errorf("create assistant session indexes: %w", err)
	}
	_, err = store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "sessionId", Value: 1},
			{Key: "sourceSequence", Value: 1},
		},
		Options: options.Index().
			SetName("uq_session_summary_source_sequence").
			SetUnique(true),
	})
	if err != nil {
		return fmt.Errorf("create assistant session summary receipt indexes: %w", err)
	}
	return nil
}

func (store *MongoSessionStore) InsertSession(
	ctx context.Context,
	session assistant.AssistantSession,
) (assistant.AssistantSession, bool, error) {
	if _, err := store.sessions.InsertOne(ctx, session); err != nil {
		if mongo.IsDuplicateKeyError(err) && session.ClientRequestID != "" {
			var existing assistant.AssistantSession
			findErr := store.sessions.FindOne(ctx, bson.M{
				"userId":          session.UserID,
				"clientRequestId": session.ClientRequestID,
			}).Decode(&existing)
			if findErr == nil {
				return existing, true, nil
			}
			return assistant.AssistantSession{}, false, findErr
		}
		return assistant.AssistantSession{}, false, err
	}
	return session, false, nil
}

func (store *MongoSessionStore) GetSession(
	ctx context.Context,
	sessionID string,
) (assistant.AssistantSession, bool, error) {
	var session assistant.AssistantSession
	err := store.sessions.FindOne(ctx, bson.M{"_id": strings.TrimSpace(sessionID)}).Decode(&session)
	if err == mongo.ErrNoDocuments {
		return assistant.AssistantSession{}, false, nil
	}
	if err != nil {
		return assistant.AssistantSession{}, false, err
	}
	return session, true, nil
}

func (store *MongoSessionStore) OwnedSessionExists(
	ctx context.Context,
	userID string,
	sessionID string,
) (bool, error) {
	count, err := store.sessions.CountDocuments(ctx, bson.M{
		"_id":    strings.TrimSpace(sessionID),
		"userId": strings.TrimSpace(userID),
	}, options.Count().SetLimit(1))
	if err != nil {
		return false, err
	}
	return count == 1, nil
}

func (store *MongoSessionStore) ListSessions(
	ctx context.Context,
	userID string,
	limit int,
	cursor string,
) ([]assistant.AssistantSession, string, error) {
	limit = clampPageLimit(limit)
	filter := bson.M{"userId": strings.TrimSpace(userID)}
	if cursor != "" {
		at, id, ok := decodeKeysetCursor(cursor)
		if !ok {
			return nil, "", fmt.Errorf("invalid sessions cursor")
		}
		filter["$or"] = bson.A{
			bson.M{"updatedAt": bson.M{"$lt": at}},
			bson.M{"updatedAt": at, "_id": bson.M{"$lt": id}},
		}
	}
	findCursor, err := store.sessions.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{{Key: "updatedAt", Value: -1}, {Key: "_id", Value: -1}}).
			SetLimit(int64(limit+1)),
	)
	if err != nil {
		return nil, "", err
	}
	defer findCursor.Close(ctx)
	items := []assistant.AssistantSession{}
	if err := findCursor.All(ctx, &items); err != nil {
		return nil, "", err
	}
	nextCursor := ""
	if len(items) > limit {
		items = items[:limit]
		last := items[len(items)-1]
		nextCursor = encodeKeysetCursor(last.UpdatedAt, last.SessionID)
	}
	return items, nextCursor, nil
}

type sessionSummaryReceiptDocument struct {
	EventID        string    `bson:"_id"`
	SessionID      string    `bson:"sessionId"`
	SummaryID      string    `bson:"summaryId"`
	SourceSequence int64     `bson:"sourceSequence"`
	CreatedAt      time.Time `bson:"createdAt"`
}

func (store *MongoSessionStore) CommitSessionSummary(
	ctx context.Context,
	commit sessionports.SessionSummaryCommit,
) (sessionports.SessionSummaryCommitResult, error) {
	if err := validateSessionSummaryCommit(commit); err != nil {
		return sessionports.SessionSummaryCommitResult{}, err
	}
	mongoSession, err := store.sessions.Database().Client().StartSession()
	if err != nil {
		return sessionports.SessionSummaryCommitResult{}, fmt.Errorf(
			"start assistant session summary transaction: %w",
			err,
		)
	}
	defer mongoSession.EndSession(ctx)
	result := sessionports.SessionSummaryCommitResult{}
	_, err = mongoSession.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		var receipt sessionSummaryReceiptDocument
		findErr := store.receipts.FindOne(txCtx, bson.M{
			"_id": commit.CompletionEventID,
		}).Decode(&receipt)
		switch {
		case findErr == nil:
			if receipt.SessionID != commit.SessionID {
				return nil, fmt.Errorf(
					"assistant session summary completion event conflicts with prior receipt",
				)
			}
			result.Replayed = true
			return nil, nil
		case !errors.Is(findErr, mongo.ErrNoDocuments):
			return nil, findErr
		}
		update, updateErr := store.sessions.UpdateOne(txCtx, bson.M{
			"_id":                   commit.SessionID,
			"summaryVersion":        commit.ExpectedVersion,
			"summarySourceSequence": commit.ExpectedSourceSequence,
		}, bson.M{
			"$set": bson.M{
				"summary":               commit.Summary.Text,
				"contextSummary":        commit.Summary,
				"summarySourceSequence": commit.NextSourceSequence,
				"summaryVersion":        commit.ExpectedVersion + 1,
				"updatedAt":             commit.UpdatedAt.UTC(),
			},
			"$inc": bson.M{"completionSequence": 1},
		})
		if updateErr != nil {
			return nil, updateErr
		}
		if update.MatchedCount != 1 {
			result.Conflict = true
			return nil, nil
		}
		_, insertErr := store.receipts.InsertOne(txCtx, sessionSummaryReceiptDocument{
			EventID:        commit.CompletionEventID,
			SessionID:      commit.SessionID,
			SummaryID:      commit.Summary.SummaryID,
			SourceSequence: commit.NextSourceSequence,
			CreatedAt:      commit.UpdatedAt.UTC(),
		})
		if insertErr != nil {
			return nil, insertErr
		}
		result.Applied = true
		return nil, nil
	})
	if err != nil {
		return sessionports.SessionSummaryCommitResult{}, err
	}
	return result, nil
}

// MemorySessionStore is a local-contract double; production wiring rejects it.
type MemorySessionStore struct {
	mu       sync.RWMutex
	sessions map[string]assistant.AssistantSession
	receipts map[string]sessionSummaryReceiptDocument
}

func NewMemorySessionStore() *MemorySessionStore {
	return &MemorySessionStore{
		sessions: map[string]assistant.AssistantSession{},
		receipts: map[string]sessionSummaryReceiptDocument{},
	}
}

func (store *MemorySessionStore) InsertSession(
	_ context.Context,
	session assistant.AssistantSession,
) (assistant.AssistantSession, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if session.ClientRequestID != "" {
		for _, existing := range store.sessions {
			if existing.UserID == session.UserID && existing.ClientRequestID == session.ClientRequestID {
				return existing, true, nil
			}
		}
	}
	store.sessions[session.SessionID] = session
	return session, false, nil
}

func (store *MemorySessionStore) GetSession(
	_ context.Context,
	sessionID string,
) (assistant.AssistantSession, bool, error) {
	store.mu.RLock()
	defer store.mu.RUnlock()
	session, ok := store.sessions[strings.TrimSpace(sessionID)]
	return session, ok, nil
}

func (store *MemorySessionStore) OwnedSessionExists(
	_ context.Context,
	userID string,
	sessionID string,
) (bool, error) {
	store.mu.RLock()
	defer store.mu.RUnlock()
	session, ok := store.sessions[strings.TrimSpace(sessionID)]
	return ok && session.UserID == strings.TrimSpace(userID), nil
}

func (store *MemorySessionStore) ListSessions(
	_ context.Context,
	userID string,
	limit int,
	cursor string,
) ([]assistant.AssistantSession, string, error) {
	limit = clampPageLimit(limit)
	store.mu.RLock()
	defer store.mu.RUnlock()
	items := []assistant.AssistantSession{}
	for _, session := range store.sessions {
		if session.UserID == strings.TrimSpace(userID) {
			items = append(items, session)
		}
	}
	sort.Slice(items, func(i, j int) bool {
		if !items[i].UpdatedAt.Equal(items[j].UpdatedAt) {
			return items[i].UpdatedAt.After(items[j].UpdatedAt)
		}
		return items[i].SessionID > items[j].SessionID
	})
	if cursor != "" {
		at, id, ok := decodeKeysetCursor(cursor)
		if !ok {
			return nil, "", fmt.Errorf("invalid sessions cursor")
		}
		filtered := items[:0:0]
		for _, item := range items {
			if item.UpdatedAt.Before(at) ||
				(item.UpdatedAt.Equal(at) && item.SessionID < id) {
				filtered = append(filtered, item)
			}
		}
		items = filtered
	}
	nextCursor := ""
	if len(items) > limit {
		items = items[:limit]
		last := items[len(items)-1]
		nextCursor = encodeKeysetCursor(last.UpdatedAt, last.SessionID)
	}
	return items, nextCursor, nil
}

func (store *MemorySessionStore) CommitSessionSummary(
	_ context.Context,
	commit sessionports.SessionSummaryCommit,
) (sessionports.SessionSummaryCommitResult, error) {
	if err := validateSessionSummaryCommit(commit); err != nil {
		return sessionports.SessionSummaryCommitResult{}, err
	}
	store.mu.Lock()
	defer store.mu.Unlock()
	if receipt, ok := store.receipts[commit.CompletionEventID]; ok {
		if receipt.SessionID != commit.SessionID {
			return sessionports.SessionSummaryCommitResult{}, fmt.Errorf(
				"assistant session summary completion event conflicts with prior receipt",
			)
		}
		return sessionports.SessionSummaryCommitResult{Replayed: true}, nil
	}
	session, ok := store.sessions[commit.SessionID]
	if !ok || session.SummaryVersion != commit.ExpectedVersion ||
		session.SummarySourceSequence != commit.ExpectedSourceSequence {
		return sessionports.SessionSummaryCommitResult{Conflict: true}, nil
	}
	session.Summary = commit.Summary.Text
	session.ContextSummary = &commit.Summary
	session.SummarySourceSequence = commit.NextSourceSequence
	session.SummaryVersion = commit.ExpectedVersion + 1
	session.CompletionSequence++
	session.UpdatedAt = commit.UpdatedAt.UTC()
	store.sessions[session.SessionID] = session
	store.receipts[commit.CompletionEventID] = sessionSummaryReceiptDocument{
		EventID:        commit.CompletionEventID,
		SessionID:      commit.SessionID,
		SummaryID:      commit.Summary.SummaryID,
		SourceSequence: commit.NextSourceSequence,
		CreatedAt:      commit.UpdatedAt.UTC(),
	}
	return sessionports.SessionSummaryCommitResult{Applied: true}, nil
}

func validateSessionSummaryCommit(commit sessionports.SessionSummaryCommit) error {
	if strings.TrimSpace(commit.CompletionEventID) == "" ||
		strings.TrimSpace(commit.SessionID) == "" ||
		commit.ExpectedVersion < 0 || commit.ExpectedSourceSequence < 0 ||
		commit.NextSourceSequence <= commit.ExpectedSourceSequence ||
		strings.TrimSpace(commit.Summary.SummaryID) == "" ||
		strings.TrimSpace(commit.Summary.Text) == "" ||
		strings.TrimSpace(commit.Summary.FromTurnID) == "" ||
		strings.TrimSpace(commit.Summary.ToTurnID) == "" ||
		commit.Summary.TurnCount <= 0 || commit.UpdatedAt.IsZero() {
		return fmt.Errorf("assistant session summary commit is invalid")
	}
	return nil
}
