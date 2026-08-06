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

// ErrSessionOutboxClaimLost reports that another relay owner took over the
// claim before this owner could mark the event published.
var ErrSessionOutboxClaimLost = errors.New("assistant session outbox claim lost")

var (
	_ sessionports.SessionStore       = (*MongoSessionStore)(nil)
	_ sessionports.SessionOutboxStore = (*MongoSessionStore)(nil)
	_ sessionports.SessionStore       = (*MemorySessionStore)(nil)
	_ sessionports.SessionOutboxStore = (*MemorySessionStore)(nil)
)

// sessionOutboxDocument mirrors the assistant learning fact outbox document so
// the service keeps exactly one transactional outbox shape.
type sessionOutboxDocument struct {
	ID           string                        `bson:"_id"`
	EventType    string                        `bson:"eventType"`
	SessionID    string                        `bson:"sessionId"`
	Payload      assistant.SessionEventPayload `bson:"payload"`
	OccurredAt   time.Time                     `bson:"occurredAt"`
	ClaimOwner   string                        `bson:"claimOwner,omitempty"`
	ClaimUntil   *time.Time                    `bson:"claimUntil,omitempty"`
	PublishedAt  *time.Time                    `bson:"publishedAt,omitempty"`
	PublishedRef string                        `bson:"publishedRef,omitempty"`
}

type MongoSessionStore struct {
	sessions *mongo.Collection
	receipts *mongo.Collection
	outbox   *mongo.Collection
}

func NewMongoSessionStore(db *mongo.Database) *MongoSessionStore {
	if db == nil {
		panic("assistant session database is required")
	}
	return &MongoSessionStore{
		sessions: db.Collection("assistant_sessions"),
		receipts: db.Collection("assistant_session_summary_receipts"),
		outbox:   db.Collection("assistant_session_outbox"),
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
	_, err = store.outbox.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "publishedAt", Value: 1},
			{Key: "claimUntil", Value: 1},
			{Key: "occurredAt", Value: 1},
		},
		Options: options.Index().
			SetName("idx_assistant_session_outbox_claimable"),
	})
	if err != nil {
		return fmt.Errorf("create assistant session outbox indexes: %w", err)
	}
	return nil
}

// InsertSession commits the aggregate and its AssistantSessionCreated domain
// event in one transaction. The event identity is derived from the sessionId,
// so a replayed creation observes the stored aggregate and appends nothing.
func (store *MongoSessionStore) InsertSession(
	ctx context.Context,
	session assistant.AssistantSession,
) (assistant.AssistantSession, bool, error) {
	mongoSession, err := store.sessions.Database().Client().StartSession()
	if err != nil {
		return assistant.AssistantSession{}, false, fmt.Errorf(
			"start assistant session create transaction: %w",
			err,
		)
	}
	defer mongoSession.EndSession(ctx)
	_, err = mongoSession.WithTransaction(
		ctx,
		func(txCtx context.Context) (any, error) {
			if _, insertErr := store.sessions.InsertOne(txCtx, session); insertErr != nil {
				return nil, insertErr
			}
			event := session.CreatedEvent()
			_, outboxErr := store.outbox.InsertOne(txCtx, sessionOutboxDocument{
				ID:         event.EventID,
				EventType:  event.EventType,
				SessionID:  event.SessionID,
				Payload:    event.Payload,
				OccurredAt: event.OccurredAt,
			})
			return nil, outboxErr
		},
	)
	if err == nil {
		return session, false, nil
	}
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

func (store *MongoSessionStore) ClaimPendingSessionEvents(
	ctx context.Context,
	ownerID string,
	lease time.Duration,
	limit int,
) ([]sessionports.PendingSessionEvent, error) {
	ownerID = strings.TrimSpace(ownerID)
	if ownerID == "" || lease <= 0 {
		return nil, fmt.Errorf(
			"assistant session outbox claim requires owner and positive lease",
		)
	}
	if limit <= 0 || limit > 512 {
		limit = 128
	}
	events := make([]sessionports.PendingSessionEvent, 0, limit)
	for len(events) < limit {
		now := time.Now().UTC()
		var document sessionOutboxDocument
		err := store.outbox.FindOneAndUpdate(
			ctx,
			bson.M{
				"publishedAt": bson.M{"$exists": false},
				"$or": bson.A{
					bson.M{"claimUntil": bson.M{"$exists": false}},
					bson.M{"claimUntil": bson.M{"$lte": now}},
				},
			},
			bson.M{"$set": bson.M{
				"claimOwner": ownerID,
				"claimUntil": now.Add(lease),
			}},
			options.FindOneAndUpdate().
				SetSort(bson.D{{Key: "occurredAt", Value: 1}}).
				SetReturnDocument(options.After),
		).Decode(&document)
		if errors.Is(err, mongo.ErrNoDocuments) {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("claim assistant session outbox: %w", err)
		}
		events = append(events, sessionports.PendingSessionEvent{
			EventID:    document.ID,
			EventType:  document.EventType,
			SessionID:  document.SessionID,
			OccurredAt: document.OccurredAt,
			Payload:    document.Payload,
		})
	}
	return events, nil
}

func (store *MongoSessionStore) MarkSessionEventPublished(
	ctx context.Context,
	eventID string,
	ownerID string,
	publishedRef string,
	publishedAt time.Time,
) error {
	result, err := store.outbox.UpdateOne(
		ctx,
		bson.M{
			"_id":         strings.TrimSpace(eventID),
			"claimOwner":  strings.TrimSpace(ownerID),
			"publishedAt": bson.M{"$exists": false},
		},
		bson.M{
			"$set": bson.M{
				"publishedAt":  publishedAt.UTC(),
				"publishedRef": strings.TrimSpace(publishedRef),
			},
			"$unset": bson.M{"claimOwner": "", "claimUntil": ""},
		},
	)
	if err != nil {
		return fmt.Errorf("mark assistant session outbox published: %w", err)
	}
	if result.MatchedCount == 0 {
		var existing sessionOutboxDocument
		loadErr := store.outbox.FindOne(
			ctx,
			bson.M{"_id": strings.TrimSpace(eventID)},
		).Decode(&existing)
		if loadErr == nil && existing.PublishedAt != nil {
			return nil
		}
		return ErrSessionOutboxClaimLost
	}
	return nil
}

func (store *MongoSessionStore) ReleaseSessionEventClaim(
	ctx context.Context,
	eventID string,
	ownerID string,
) error {
	_, err := store.outbox.UpdateOne(
		ctx,
		bson.M{
			"_id":         strings.TrimSpace(eventID),
			"claimOwner":  strings.TrimSpace(ownerID),
			"publishedAt": bson.M{"$exists": false},
		},
		bson.M{"$unset": bson.M{"claimOwner": "", "claimUntil": ""}},
	)
	if err != nil {
		return fmt.Errorf("release assistant session outbox claim: %w", err)
	}
	return nil
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
	outbox   map[string]*sessionOutboxDocument
	order    []string
}

func NewMemorySessionStore() *MemorySessionStore {
	return &MemorySessionStore{
		sessions: map[string]assistant.AssistantSession{},
		receipts: map[string]sessionSummaryReceiptDocument{},
		outbox:   map[string]*sessionOutboxDocument{},
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
	event := session.CreatedEvent()
	if _, exists := store.outbox[event.EventID]; !exists {
		store.outbox[event.EventID] = &sessionOutboxDocument{
			ID:         event.EventID,
			EventType:  event.EventType,
			SessionID:  event.SessionID,
			Payload:    event.Payload,
			OccurredAt: event.OccurredAt,
		}
		store.order = append(store.order, event.EventID)
	}
	store.sessions[session.SessionID] = session
	return session, false, nil
}

func (store *MemorySessionStore) ClaimPendingSessionEvents(
	_ context.Context,
	ownerID string,
	lease time.Duration,
	limit int,
) ([]sessionports.PendingSessionEvent, error) {
	ownerID = strings.TrimSpace(ownerID)
	if ownerID == "" || lease <= 0 {
		return nil, fmt.Errorf(
			"assistant session outbox claim requires owner and positive lease",
		)
	}
	if limit <= 0 || limit > 512 {
		limit = 128
	}
	store.mu.Lock()
	defer store.mu.Unlock()
	now := time.Now().UTC()
	claimed := make([]sessionports.PendingSessionEvent, 0, limit)
	for _, eventID := range store.order {
		if len(claimed) == limit {
			break
		}
		document := store.outbox[eventID]
		if document == nil || document.PublishedAt != nil {
			continue
		}
		if document.ClaimUntil != nil && document.ClaimUntil.After(now) {
			continue
		}
		claimUntil := now.Add(lease)
		document.ClaimOwner = ownerID
		document.ClaimUntil = &claimUntil
		claimed = append(claimed, sessionports.PendingSessionEvent{
			EventID:    document.ID,
			EventType:  document.EventType,
			SessionID:  document.SessionID,
			OccurredAt: document.OccurredAt,
			Payload:    document.Payload,
		})
	}
	return claimed, nil
}

func (store *MemorySessionStore) MarkSessionEventPublished(
	_ context.Context,
	eventID string,
	ownerID string,
	publishedRef string,
	publishedAt time.Time,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	document := store.outbox[strings.TrimSpace(eventID)]
	if document == nil {
		return ErrSessionOutboxClaimLost
	}
	if document.PublishedAt != nil {
		return nil
	}
	if document.ClaimOwner != strings.TrimSpace(ownerID) {
		return ErrSessionOutboxClaimLost
	}
	stamp := publishedAt.UTC()
	document.PublishedAt = &stamp
	document.PublishedRef = strings.TrimSpace(publishedRef)
	document.ClaimOwner = ""
	document.ClaimUntil = nil
	return nil
}

func (store *MemorySessionStore) ReleaseSessionEventClaim(
	_ context.Context,
	eventID string,
	ownerID string,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	document := store.outbox[strings.TrimSpace(eventID)]
	if document == nil || document.PublishedAt != nil ||
		document.ClaimOwner != strings.TrimSpace(ownerID) {
		return nil
	}
	document.ClaimOwner = ""
	document.ClaimUntil = nil
	return nil
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
