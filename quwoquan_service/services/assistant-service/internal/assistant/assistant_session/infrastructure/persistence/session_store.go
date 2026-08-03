package persistence

import (
	"context"
	"encoding/base64"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
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
}

func NewMongoSessionStore(db *mongo.Database) *MongoSessionStore {
	if db == nil {
		panic("assistant session database is required")
	}
	return &MongoSessionStore{sessions: db.Collection("assistant_sessions")}
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

func (store *MongoSessionStore) CompareAndSwapSessionSummary(
	ctx context.Context,
	sessionID string,
	expectedVersion int64,
	expectedSourceSequence int64,
	nextSourceSequence int64,
	summary assistant.AssistantSessionContextSummary,
	updatedAt time.Time,
) (bool, error) {
	result, err := store.sessions.UpdateOne(ctx, bson.M{
		"_id":                   strings.TrimSpace(sessionID),
		"summaryVersion":        expectedVersion,
		"summarySourceSequence": expectedSourceSequence,
	}, bson.M{
		"$set": bson.M{
			"summary":               summary.Text,
			"contextSummary":        summary,
			"summarySourceSequence": nextSourceSequence,
			"summaryVersion":        expectedVersion + 1,
			"updatedAt":             updatedAt.UTC(),
		},
	})
	if err != nil {
		return false, err
	}
	return result.MatchedCount == 1, nil
}

// MemorySessionStore is a local-contract double; production wiring rejects it.
type MemorySessionStore struct {
	mu       sync.RWMutex
	sessions map[string]assistant.AssistantSession
}

func NewMemorySessionStore() *MemorySessionStore {
	return &MemorySessionStore{sessions: map[string]assistant.AssistantSession{}}
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

func (store *MemorySessionStore) CompareAndSwapSessionSummary(
	_ context.Context,
	sessionID string,
	expectedVersion int64,
	expectedSourceSequence int64,
	nextSourceSequence int64,
	summary assistant.AssistantSessionContextSummary,
	updatedAt time.Time,
) (bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	session, ok := store.sessions[strings.TrimSpace(sessionID)]
	if !ok || session.SummaryVersion != expectedVersion ||
		session.SummarySourceSequence != expectedSourceSequence {
		return false, nil
	}
	session.Summary = summary.Text
	session.ContextSummary = &summary
	session.SummarySourceSequence = nextSourceSequence
	session.SummaryVersion = expectedVersion + 1
	session.UpdatedAt = updatedAt.UTC()
	store.sessions[session.SessionID] = session
	return true, nil
}
