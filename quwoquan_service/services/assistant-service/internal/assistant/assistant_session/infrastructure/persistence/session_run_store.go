package persistence

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/streaming"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

const assistantRunEventRetention = 7 * 24 * time.Hour

type assistantRunEventDocument struct {
	ID        string             `bson:"_id"`
	RunID     string             `bson:"runId"`
	Seq       uint64             `bson:"seq"`
	Envelope  streaming.Envelope `bson:"envelope"`
	CreatedAt time.Time          `bson:"createdAt"`
	ExpiresAt time.Time          `bson:"expiresAt"`
}

// keyset cursor 编解码：base64("<unixNano>|<id>")，不透明字符串，端侧不得解析。
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

// MongoSessionRunStore 持久化 AssistantSession（assistant_sessions）
// 与 AssistantRun/Turn（assistant_runs）两个聚合。索引契约来自
// services/assistant-service/contracts/{assistant_session,assistant_run}/storage.yaml。
type MongoSessionRunStore struct {
	sessions  *mongo.Collection
	runs      *mongo.Collection
	runEvents *mongo.Collection
}

func NewMongoSessionRunStore(db *mongo.Database) *MongoSessionRunStore {
	return &MongoSessionRunStore{
		sessions:  db.Collection("assistant_sessions"),
		runs:      db.Collection("assistant_runs"),
		runEvents: db.Collection("assistant_run_events"),
	}
}

func (s *MongoSessionRunStore) EnsureIndexes(ctx context.Context) error {
	sessionIndexes := []mongo.IndexModel{
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
	}
	if _, err := s.sessions.Indexes().CreateMany(ctx, sessionIndexes); err != nil {
		return fmt.Errorf("create assistant session indexes: %w", err)
	}
	runIndexes := []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "userId", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_runs_user_created"),
		},
		{
			Keys:    bson.D{{Key: "sessionId", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_runs_session"),
		},
		{
			Keys: bson.D{
				{Key: "sessionId", Value: 1},
				{Key: "userId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "createdAt", Value: -1},
			},
			Options: options.Index().SetName("idx_runs_context_window"),
		},
		{
			Keys: bson.D{
				{Key: "userId", Value: 1},
				{Key: "sessionId", Value: 1},
				{Key: "clientRequestId", Value: 1},
			},
			Options: options.Index().
				SetName("uq_runs_client_request").
				SetUnique(true).
				SetPartialFilterExpression(bson.M{
					"clientRequestId": bson.M{"$type": "string"},
				}),
		},
		{
			Keys:    bson.D{{Key: "skillId", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_runs_skill").SetSparse(true),
		},
		{
			Keys:    bson.D{{Key: "status", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_runs_status"),
		},
	}
	if _, err := s.runs.Indexes().CreateMany(ctx, runIndexes); err != nil {
		return fmt.Errorf("create assistant run indexes: %w", err)
	}
	runEventIndexes := []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "runId", Value: 1}, {Key: "seq", Value: 1}},
			Options: options.Index().SetName("uq_run_events_run_seq").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().SetName("idx_run_events_expire").SetExpireAfterSeconds(0),
		},
	}
	if _, err := s.runEvents.Indexes().CreateMany(ctx, runEventIndexes); err != nil {
		return fmt.Errorf("create assistant run event indexes: %w", err)
	}
	return nil
}

func (s *MongoSessionRunStore) InsertSession(
	ctx context.Context,
	session assistant.AssistantSession,
) (assistant.AssistantSession, bool, error) {
	if _, err := s.sessions.InsertOne(ctx, session); err != nil {
		if mongo.IsDuplicateKeyError(err) && session.ClientRequestID != "" {
			var existing assistant.AssistantSession
			findErr := s.sessions.FindOne(ctx, bson.M{
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

func (s *MongoSessionRunStore) GetSession(
	ctx context.Context,
	sessionID string,
) (assistant.AssistantSession, bool, error) {
	var session assistant.AssistantSession
	err := s.sessions.FindOne(ctx, bson.M{"_id": sessionID}).Decode(&session)
	if err == mongo.ErrNoDocuments {
		return assistant.AssistantSession{}, false, nil
	}
	if err != nil {
		return assistant.AssistantSession{}, false, err
	}
	return session, true, nil
}

func (s *MongoSessionRunStore) OwnedSessionExists(
	ctx context.Context,
	userID string,
	sessionID string,
) (bool, error) {
	count, err := s.sessions.CountDocuments(ctx, bson.M{
		"_id":    strings.TrimSpace(sessionID),
		"userId": strings.TrimSpace(userID),
	}, options.Count().SetLimit(1))
	if err != nil {
		return false, err
	}
	return count == 1, nil
}

func (s *MongoSessionRunStore) UpdateSessionTurnPointer(
	ctx context.Context,
	sessionID string,
	activeTurnID string,
	lastTurnID string,
	updatedAt time.Time,
) error {
	_, err := s.sessions.UpdateOne(ctx, bson.M{"_id": sessionID}, bson.M{
		"$set": bson.M{
			"activeTurnId": activeTurnID,
			"lastTurnId":   lastTurnID,
			"updatedAt":    updatedAt.UTC(),
		},
	})
	return err
}

func (s *MongoSessionRunStore) CompareAndSwapSessionSummary(
	ctx context.Context,
	sessionID string,
	expectedVersion int64,
	expectedSourceSequence int64,
	nextSourceSequence int64,
	summary assistant.AssistantSessionContextSummary,
	updatedAt time.Time,
) (bool, error) {
	result, err := s.sessions.UpdateOne(ctx, bson.M{
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

func (s *MongoSessionRunStore) InsertTurn(
	ctx context.Context,
	turn assistant.AssistantTurn,
) (assistant.AssistantTurn, bool, error) {
	if _, err := s.runs.InsertOne(ctx, turn); err != nil {
		if mongo.IsDuplicateKeyError(err) && turn.ClientRequestID != "" {
			var existing assistant.AssistantTurn
			findErr := s.runs.FindOne(ctx, bson.M{
				"userId":          turn.UserID,
				"sessionId":       turn.SessionID,
				"clientRequestId": turn.ClientRequestID,
			}).Decode(&existing)
			if findErr == nil {
				return existing, true, nil
			}
			return assistant.AssistantTurn{}, false, findErr
		}
		return assistant.AssistantTurn{}, false, err
	}
	return turn, false, nil
}

func (s *MongoSessionRunStore) GetTurn(
	ctx context.Context,
	turnID string,
) (assistant.AssistantTurn, bool, error) {
	var turn assistant.AssistantTurn
	err := s.runs.FindOne(ctx, bson.M{"_id": turnID}).Decode(&turn)
	if err == mongo.ErrNoDocuments {
		return assistant.AssistantTurn{}, false, nil
	}
	if err != nil {
		return assistant.AssistantTurn{}, false, err
	}
	return turn, true, nil
}

func (s *MongoSessionRunStore) GetTurnByClientRequest(
	ctx context.Context,
	userID string,
	sessionID string,
	clientRequestID string,
) (assistant.AssistantTurn, bool, error) {
	var turn assistant.AssistantTurn
	err := s.runs.FindOne(ctx, bson.M{
		"userId":          strings.TrimSpace(userID),
		"sessionId":       strings.TrimSpace(sessionID),
		"clientRequestId": strings.TrimSpace(clientRequestID),
	}).Decode(&turn)
	if err == mongo.ErrNoDocuments {
		return assistant.AssistantTurn{}, false, nil
	}
	if err != nil {
		return assistant.AssistantTurn{}, false, err
	}
	return turn, true, nil
}

// CompleteTurn 以内部 CAS 把 running turn 推进到终态；已终态时幂等返回存量。
func (s *MongoSessionRunStore) CompleteTurn(
	ctx context.Context,
	turn assistant.AssistantTurn,
) (assistant.AssistantTurn, error) {
	session, err := s.runs.Database().Client().StartSession()
	if err != nil {
		return assistant.AssistantTurn{}, err
	}
	defer session.EndSession(ctx)

	var stored assistant.AssistantTurn
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		current, found, getErr := s.GetTurn(txCtx, turn.TurnID)
		if getErr != nil {
			return nil, getErr
		}
		if !found {
			return nil, mongo.ErrNoDocuments
		}
		if current.Status != "running" {
			if current.Status == turn.Status &&
				turn.StreamState.LastSeq > current.StreamState.LastSeq {
				_, updateErr := s.runs.UpdateOne(
					txCtx,
					bson.M{
						"_id":    turn.TurnID,
						"status": turn.Status,
						"$or": bson.A{
							bson.M{"streamState.lastSeq": bson.M{"$lt": turn.StreamState.LastSeq}},
							bson.M{"streamState.lastSeq": bson.M{"$exists": false}},
						},
					},
					bson.M{"$set": bson.M{
						"streamState":      turn.StreamState,
						"terminalSnapshot": turn.TerminalSnapshot,
						"completedAt":      turn.CompletedAt,
					}},
				)
				if updateErr != nil {
					return nil, updateErr
				}
				current.StreamState = turn.StreamState
				current.TerminalSnapshot = turn.TerminalSnapshot
				current.CompletedAt = turn.CompletedAt
			}
			stored = current
			return nil, nil
		}

		var aggregate assistant.AssistantSession
		if sequenceErr := s.sessions.FindOneAndUpdate(
			txCtx,
			bson.M{"_id": current.SessionID},
			bson.M{"$inc": bson.M{"completionSequence": 1}},
			options.FindOneAndUpdate().SetReturnDocument(options.After),
		).Decode(&aggregate); sequenceErr != nil {
			return nil, sequenceErr
		}
		turn.CompletionSequence = aggregate.CompletionSequence
		result, updateErr := s.runs.UpdateOne(
			txCtx,
			bson.M{"_id": turn.TurnID, "status": "running"},
			bson.M{"$set": bson.M{
				"status":             turn.Status,
				"skillId":            turn.SkillID,
				"domainId":           turn.DomainID,
				"streamState":        turn.StreamState,
				"terminalSnapshot":   turn.TerminalSnapshot,
				"completedAt":        turn.CompletedAt,
				"completionSequence": turn.CompletionSequence,
			}},
		)
		if updateErr != nil {
			return nil, updateErr
		}
		if result.MatchedCount != 1 {
			return nil, fmt.Errorf("assistant turn terminal CAS conflict")
		}
		canonical, found, getErr := s.GetTurn(txCtx, turn.TurnID)
		if getErr != nil {
			return nil, getErr
		}
		if !found {
			return nil, mongo.ErrNoDocuments
		}
		stored = canonical
		return nil, nil
	})
	if err != nil {
		return assistant.AssistantTurn{}, err
	}
	return stored, nil
}

func (s *MongoSessionRunStore) ListCompletedTurns(
	ctx context.Context,
	userID string,
	sessionID string,
	limit int,
) ([]assistant.AssistantTurn, error) {
	if limit <= 0 || limit > 50 {
		limit = 6
	}
	cursor, err := s.runs.Find(ctx, bson.M{
		"sessionId": sessionID,
		"userId":    userID,
		"status":    "completed",
	}, options.Find().
		SetSort(bson.D{{Key: "createdAt", Value: -1}}).
		SetLimit(int64(limit)))
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	turns := []assistant.AssistantTurn{}
	if err := cursor.All(ctx, &turns); err != nil {
		return nil, err
	}
	// 按 createdAt 升序返回，供上下文窗口按时间正序拼接。
	sort.Slice(turns, func(i, j int) bool {
		return turns[i].CreatedAt.Before(turns[j].CreatedAt)
	})
	return turns, nil
}

func (s *MongoSessionRunStore) ListCompletedTurnsAfterSequence(
	ctx context.Context,
	userID string,
	sessionID string,
	afterSequence int64,
	limit int,
) ([]assistant.AssistantTurn, error) {
	if limit <= 0 || limit > 500 {
		limit = 200
	}
	cursor, err := s.runs.Find(ctx, bson.M{
		"sessionId":          strings.TrimSpace(sessionID),
		"userId":             strings.TrimSpace(userID),
		"status":             "completed",
		"completionSequence": bson.M{"$gt": afterSequence},
	}, options.Find().
		SetSort(bson.D{{Key: "completionSequence", Value: 1}}).
		SetLimit(int64(limit)))
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	turns := []assistant.AssistantTurn{}
	if err := cursor.All(ctx, &turns); err != nil {
		return nil, err
	}
	return turns, nil
}

// ListSessions 以 updatedAt desc + _id desc 的 keyset 分页返回 owner 会话。
func (s *MongoSessionRunStore) ListSessions(
	ctx context.Context,
	userID string,
	limit int,
	cursor string,
) ([]assistant.AssistantSession, string, error) {
	limit = clampPageLimit(limit)
	filter := bson.M{"userId": userID}
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
	findCursor, err := s.sessions.Find(ctx, filter, options.Find().
		SetSort(bson.D{{Key: "updatedAt", Value: -1}, {Key: "_id", Value: -1}}).
		SetLimit(int64(limit+1)))
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

func (s *MongoSessionRunStore) AppendRunEvent(
	ctx context.Context,
	runID string,
	envelope streaming.Envelope,
) error {
	runID, envelope, err := normalizeAssistantRunEventForAppend(runID, envelope)
	if err != nil {
		return err
	}
	existing, found, err := s.findRunEvent(ctx, runID, envelope.Seq)
	if err != nil {
		return err
	}
	if found {
		return reconcileAssistantRunEventReplay(existing.Envelope, envelope)
	}
	if envelope.Seq > 1 {
		if _, predecessorFound, predecessorErr := s.findRunEvent(
			ctx,
			runID,
			envelope.Seq-1,
		); predecessorErr != nil {
			return predecessorErr
		} else if !predecessorFound {
			return fmt.Errorf(
				"assistant run event protocol violation: run %q cannot append seq %d before seq %d",
				runID,
				envelope.Seq,
				envelope.Seq-1,
			)
		}
	}
	createdAt := envelope.CreatedAt
	document := assistantRunEventDocument{
		ID:        fmt.Sprintf("%s:%020d", runID, envelope.Seq),
		RunID:     runID,
		Seq:       envelope.Seq,
		Envelope:  envelope,
		CreatedAt: createdAt,
		ExpiresAt: createdAt.Add(assistantRunEventRetention),
	}
	if _, err := s.runEvents.InsertOne(ctx, document); err != nil {
		if mongo.IsDuplicateKeyError(err) {
			existing, found, lookupErr := s.findRunEvent(ctx, runID, envelope.Seq)
			if lookupErr != nil {
				return lookupErr
			}
			if !found {
				return fmt.Errorf(
					"assistant run event duplicate write was not readable: run %q seq %d",
					runID,
					envelope.Seq,
				)
			}
			return reconcileAssistantRunEventReplay(existing.Envelope, envelope)
		}
		return err
	}
	return nil
}

func (s *MongoSessionRunStore) findRunEvent(
	ctx context.Context,
	runID string,
	seq uint64,
) (assistantRunEventDocument, bool, error) {
	var document assistantRunEventDocument
	err := s.runEvents.FindOne(
		ctx,
		bson.M{"runId": runID, "seq": seq},
	).Decode(&document)
	if err == nil {
		return document, true, nil
	}
	if err == mongo.ErrNoDocuments {
		return assistantRunEventDocument{}, false, nil
	}
	return assistantRunEventDocument{}, false, err
}

func (s *MongoSessionRunStore) ListRunEvents(
	ctx context.Context,
	runID string,
	afterSeq uint64,
	limit int,
) ([]streaming.Envelope, error) {
	if limit <= 0 || limit > 200 {
		limit = 100
	}
	cursor, err := s.runEvents.Find(
		ctx,
		bson.M{"runId": runID, "seq": bson.M{"$gt": afterSeq}},
		options.Find().SetSort(bson.D{{Key: "seq", Value: 1}}).SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	events := make([]streaming.Envelope, 0)
	for cursor.Next(ctx) {
		var document assistantRunEventDocument
		if err := cursor.Decode(&document); err != nil {
			return nil, err
		}
		events = append(events, document.Envelope.Normalized())
	}
	if err := cursor.Err(); err != nil {
		return nil, err
	}
	if err := validateAssistantRunEventSequence(runID, afterSeq, events); err != nil {
		return nil, err
	}
	return events, nil
}

// MemorySessionRunStore 仅供测试装配；生产启动经
// TestRuntimeDependenciesRejectMissingOrMemoryStorage 拒绝 memory 变体。
type MemorySessionRunStore struct {
	mu        sync.RWMutex
	sessions  map[string]assistant.AssistantSession
	turns     map[string]assistant.AssistantTurn
	runEvents map[string][]streaming.Envelope
}

func NewMemorySessionRunStore() *MemorySessionRunStore {
	return &MemorySessionRunStore{
		sessions:  map[string]assistant.AssistantSession{},
		turns:     map[string]assistant.AssistantTurn{},
		runEvents: map[string][]streaming.Envelope{},
	}
}

func (s *MemorySessionRunStore) InsertSession(
	_ context.Context,
	session assistant.AssistantSession,
) (assistant.AssistantSession, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if session.ClientRequestID != "" {
		for _, existing := range s.sessions {
			if existing.UserID == session.UserID &&
				existing.ClientRequestID == session.ClientRequestID {
				return existing, true, nil
			}
		}
	}
	s.sessions[session.SessionID] = session
	return session, false, nil
}

func (s *MemorySessionRunStore) GetSession(
	_ context.Context,
	sessionID string,
) (assistant.AssistantSession, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	session, ok := s.sessions[strings.TrimSpace(sessionID)]
	return session, ok, nil
}

func (s *MemorySessionRunStore) OwnedSessionExists(
	_ context.Context,
	userID string,
	sessionID string,
) (bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	session, ok := s.sessions[strings.TrimSpace(sessionID)]
	return ok && session.UserID == strings.TrimSpace(userID), nil
}

func (s *MemorySessionRunStore) UpdateSessionTurnPointer(
	_ context.Context,
	sessionID string,
	activeTurnID string,
	lastTurnID string,
	updatedAt time.Time,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	session, ok := s.sessions[sessionID]
	if !ok {
		return nil
	}
	session.ActiveTurnID = activeTurnID
	session.LastTurnID = lastTurnID
	session.UpdatedAt = updatedAt.UTC()
	s.sessions[sessionID] = session
	return nil
}

func (s *MemorySessionRunStore) CompareAndSwapSessionSummary(
	_ context.Context,
	sessionID string,
	expectedVersion int64,
	expectedSourceSequence int64,
	nextSourceSequence int64,
	summary assistant.AssistantSessionContextSummary,
	updatedAt time.Time,
) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	session, ok := s.sessions[strings.TrimSpace(sessionID)]
	if !ok ||
		session.SummaryVersion != expectedVersion ||
		session.SummarySourceSequence != expectedSourceSequence {
		return false, nil
	}
	session.Summary = summary.Text
	session.ContextSummary = &summary
	session.SummarySourceSequence = nextSourceSequence
	session.SummaryVersion = expectedVersion + 1
	session.UpdatedAt = updatedAt.UTC()
	s.sessions[session.SessionID] = session
	return true, nil
}

func (s *MemorySessionRunStore) InsertTurn(
	_ context.Context,
	turn assistant.AssistantTurn,
) (assistant.AssistantTurn, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if turn.ClientRequestID != "" {
		for _, existing := range s.turns {
			if existing.UserID == turn.UserID &&
				existing.SessionID == turn.SessionID &&
				existing.ClientRequestID == turn.ClientRequestID {
				return existing, true, nil
			}
		}
	}
	s.turns[turn.TurnID] = turn
	if turn.CompletionSequence > 0 {
		session := s.sessions[turn.SessionID]
		if turn.CompletionSequence > session.CompletionSequence {
			session.CompletionSequence = turn.CompletionSequence
			s.sessions[turn.SessionID] = session
		}
	}
	return turn, false, nil
}

func (s *MemorySessionRunStore) GetTurn(
	_ context.Context,
	turnID string,
) (assistant.AssistantTurn, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	turn, ok := s.turns[strings.TrimSpace(turnID)]
	return turn, ok, nil
}

func (s *MemorySessionRunStore) GetTurnByClientRequest(
	_ context.Context,
	userID string,
	sessionID string,
	clientRequestID string,
) (assistant.AssistantTurn, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	userID = strings.TrimSpace(userID)
	sessionID = strings.TrimSpace(sessionID)
	clientRequestID = strings.TrimSpace(clientRequestID)
	for _, turn := range s.turns {
		if turn.UserID == userID &&
			turn.SessionID == sessionID &&
			turn.ClientRequestID == clientRequestID {
			return turn, true, nil
		}
	}
	return assistant.AssistantTurn{}, false, nil
}

func (s *MemorySessionRunStore) CompleteTurn(
	_ context.Context,
	turn assistant.AssistantTurn,
) (assistant.AssistantTurn, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	stored, ok := s.turns[turn.TurnID]
	if !ok {
		return assistant.AssistantTurn{}, mongo.ErrNoDocuments
	}
	if stored.Status != "running" {
		if stored.Status == turn.Status && turn.StreamState.LastSeq > stored.StreamState.LastSeq {
			stored.StreamState = turn.StreamState
			stored.TerminalSnapshot = turn.TerminalSnapshot
			stored.CompletedAt = turn.CompletedAt
			s.turns[turn.TurnID] = stored
		}
		return stored, nil
	}
	session := s.sessions[stored.SessionID]
	session.CompletionSequence++
	turn.CompletionSequence = session.CompletionSequence
	s.sessions[stored.SessionID] = session
	s.turns[turn.TurnID] = turn
	return turn, nil
}

func (s *MemorySessionRunStore) ListCompletedTurns(
	_ context.Context,
	userID string,
	sessionID string,
	limit int,
) ([]assistant.AssistantTurn, error) {
	if limit <= 0 || limit > 50 {
		limit = 6
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	turns := []assistant.AssistantTurn{}
	for _, turn := range s.turns {
		if turn.UserID == userID &&
			turn.SessionID == sessionID &&
			turn.Status == "completed" {
			turns = append(turns, turn)
		}
	}
	sort.Slice(turns, func(i, j int) bool {
		return turns[i].CreatedAt.Before(turns[j].CreatedAt)
	})
	if len(turns) > limit {
		turns = turns[len(turns)-limit:]
	}
	return turns, nil
}

func (s *MemorySessionRunStore) ListCompletedTurnsAfterSequence(
	_ context.Context,
	userID string,
	sessionID string,
	afterSequence int64,
	limit int,
) ([]assistant.AssistantTurn, error) {
	if limit <= 0 || limit > 500 {
		limit = 200
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	turns := []assistant.AssistantTurn{}
	for _, turn := range s.turns {
		if turn.UserID == strings.TrimSpace(userID) &&
			turn.SessionID == strings.TrimSpace(sessionID) &&
			turn.Status == "completed" &&
			turn.CompletionSequence > afterSequence {
			turns = append(turns, turn)
		}
	}
	sort.Slice(turns, func(i, j int) bool {
		return turns[i].CompletionSequence < turns[j].CompletionSequence
	})
	if len(turns) > limit {
		turns = turns[:limit]
	}
	return turns, nil
}

func (s *MemorySessionRunStore) ListSessions(
	_ context.Context,
	userID string,
	limit int,
	cursor string,
) ([]assistant.AssistantSession, string, error) {
	limit = clampPageLimit(limit)
	s.mu.RLock()
	defer s.mu.RUnlock()
	items := []assistant.AssistantSession{}
	for _, session := range s.sessions {
		if session.UserID == userID {
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

func (s *MemorySessionRunStore) AppendRunEvent(
	_ context.Context,
	runID string,
	envelope streaming.Envelope,
) error {
	var err error
	runID, envelope, err = normalizeAssistantRunEventForAppend(runID, envelope)
	if err != nil {
		return err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	existingEvents := s.runEvents[runID]
	for _, existing := range existingEvents {
		if existing.Seq == envelope.Seq {
			return reconcileAssistantRunEventReplay(existing, envelope)
		}
	}
	expectedSeq := uint64(1)
	if len(existingEvents) > 0 {
		expectedSeq = existingEvents[len(existingEvents)-1].Seq + 1
	}
	if envelope.Seq != expectedSeq {
		return fmt.Errorf(
			"assistant run event protocol violation: run %q sequence %d, want %d",
			runID,
			envelope.Seq,
			expectedSeq,
		)
	}
	s.runEvents[runID] = append(existingEvents, envelope)
	return nil
}

func (s *MemorySessionRunStore) ListRunEvents(
	_ context.Context,
	runID string,
	afterSeq uint64,
	limit int,
) ([]streaming.Envelope, error) {
	if limit <= 0 || limit > 200 {
		limit = 100
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	events := make([]streaming.Envelope, 0)
	for _, envelope := range s.runEvents[runID] {
		if envelope.Seq <= afterSeq {
			continue
		}
		events = append(events, envelope)
		if len(events) == limit {
			break
		}
	}
	if err := validateAssistantRunEventSequence(runID, afterSeq, events); err != nil {
		return nil, err
	}
	return events, nil
}

func normalizeAssistantRunEventForAppend(
	runID string,
	envelope streaming.Envelope,
) (string, streaming.Envelope, error) {
	runID = strings.TrimSpace(runID)
	if runID == "" {
		return "", streaming.Envelope{}, fmt.Errorf(
			"assistant run event protocol violation: missing run id",
		)
	}
	if envelope.Seq == 0 {
		return "", streaming.Envelope{}, fmt.Errorf(
			"assistant run event protocol violation: run %q sequence must start at 1",
			runID,
		)
	}
	envelope = envelope.Normalized()
	if envelope.StreamID != runID {
		return "", streaming.Envelope{}, fmt.Errorf(
			"assistant run event protocol violation: event stream %q does not match run %q",
			envelope.StreamID,
			runID,
		)
	}
	if envelope.EventID == "" || envelope.EventType == "" ||
		envelope.Event != envelope.EventType {
		return "", streaming.Envelope{}, fmt.Errorf(
			"assistant run event protocol violation: run %q has incomplete event identity",
			runID,
		)
	}
	return runID, envelope, nil
}

func reconcileAssistantRunEventReplay(
	existing streaming.Envelope,
	replayed streaming.Envelope,
) error {
	existingJSON, existingErr := json.Marshal(existing.Normalized())
	replayedJSON, replayedErr := json.Marshal(replayed.Normalized())
	if existingErr == nil && replayedErr == nil &&
		bytes.Equal(existingJSON, replayedJSON) {
		return nil
	}
	return fmt.Errorf(
		"assistant run event protocol violation: duplicate sequence %d has divergent payload",
		replayed.Seq,
	)
}

func validateAssistantRunEventSequence(
	runID string,
	afterSeq uint64,
	events []streaming.Envelope,
) error {
	// afterSeq=0 is an initial read. Event TTL may have removed a complete
	// prefix of a terminal run, so only demand continuity from the first
	// retained event. A resumed stream, however, must continue exactly after
	// the caller's acknowledged sequence.
	previousSeq := afterSeq
	requireNext := afterSeq > 0
	for _, envelope := range events {
		if requireNext && envelope.Seq != previousSeq+1 {
			return fmt.Errorf(
				"assistant run event protocol violation: run %q sequence %d, want %d",
				runID,
				envelope.Seq,
				previousSeq+1,
			)
		}
		previousSeq = envelope.Seq
		requireNext = true
	}
	return nil
}
