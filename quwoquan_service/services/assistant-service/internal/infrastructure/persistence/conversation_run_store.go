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

	"quwoquan_service/runtime/streaming"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

// terminalTurnStatuses 是 ListTurns 暴露的终态集合；running 中的 turn 不进入
// 历史切片（其可见性由 SSE/GetAssistantRun 承载）。
var terminalTurnStatuses = []string{"completed", "failed", "cancelled"}

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

// MongoConversationRunStore 持久化 AssistantConversation（assistant_conversations）
// 与 AssistantRun/Turn（assistant_runs）两个聚合。索引契约来自
// contracts/metadata/assistant/{assistant_conversation,assistant_run}/storage.yaml。
type MongoConversationRunStore struct {
	conversations *mongo.Collection
	runs          *mongo.Collection
	runEvents     *mongo.Collection
}

func NewMongoConversationRunStore(db *mongo.Database) *MongoConversationRunStore {
	return &MongoConversationRunStore{
		conversations: db.Collection("assistant_conversations"),
		runs:          db.Collection("assistant_runs"),
		runEvents:     db.Collection("assistant_run_events"),
	}
}

func (s *MongoConversationRunStore) EnsureIndexes(ctx context.Context) error {
	conversationIndexes := []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "userId", Value: 1}, {Key: "updatedAt", Value: -1}},
			Options: options.Index().SetName("idx_conversations_user_updated"),
		},
		{
			Keys: bson.D{{Key: "userId", Value: 1}, {Key: "clientRequestId", Value: 1}},
			Options: options.Index().
				SetName("uq_conversations_client_request").
				SetUnique(true).
				SetPartialFilterExpression(bson.M{
					"clientRequestId": bson.M{"$type": "string"},
				}),
		},
	}
	if _, err := s.conversations.Indexes().CreateMany(ctx, conversationIndexes); err != nil {
		return fmt.Errorf("create assistant conversation indexes: %w", err)
	}
	runIndexes := []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "userId", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_runs_user_created"),
		},
		{
			Keys:    bson.D{{Key: "conversationId", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_runs_conversation"),
		},
		{
			Keys: bson.D{
				{Key: "conversationId", Value: 1},
				{Key: "userId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "createdAt", Value: -1},
			},
			Options: options.Index().SetName("idx_runs_context_window"),
		},
		{
			Keys: bson.D{
				{Key: "userId", Value: 1},
				{Key: "conversationId", Value: 1},
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

func (s *MongoConversationRunStore) InsertConversation(
	ctx context.Context,
	conversation assistant.AssistantConversation,
) (assistant.AssistantConversation, bool, error) {
	if _, err := s.conversations.InsertOne(ctx, conversation); err != nil {
		if mongo.IsDuplicateKeyError(err) && conversation.ClientRequestID != "" {
			var existing assistant.AssistantConversation
			findErr := s.conversations.FindOne(ctx, bson.M{
				"userId":          conversation.UserID,
				"clientRequestId": conversation.ClientRequestID,
			}).Decode(&existing)
			if findErr == nil {
				return existing, true, nil
			}
			return assistant.AssistantConversation{}, false, findErr
		}
		return assistant.AssistantConversation{}, false, err
	}
	return conversation, false, nil
}

func (s *MongoConversationRunStore) GetConversation(
	ctx context.Context,
	conversationID string,
) (assistant.AssistantConversation, bool, error) {
	var conversation assistant.AssistantConversation
	err := s.conversations.FindOne(ctx, bson.M{"_id": conversationID}).Decode(&conversation)
	if err == mongo.ErrNoDocuments {
		return assistant.AssistantConversation{}, false, nil
	}
	if err != nil {
		return assistant.AssistantConversation{}, false, err
	}
	return conversation, true, nil
}

func (s *MongoConversationRunStore) OwnedConversationExists(
	ctx context.Context,
	userID string,
	conversationID string,
) (bool, error) {
	count, err := s.conversations.CountDocuments(ctx, bson.M{
		"_id":    strings.TrimSpace(conversationID),
		"userId": strings.TrimSpace(userID),
	}, options.Count().SetLimit(1))
	if err != nil {
		return false, err
	}
	return count == 1, nil
}

func (s *MongoConversationRunStore) UpdateConversationTurnPointer(
	ctx context.Context,
	conversationID string,
	activeTurnID string,
	lastTurnID string,
	updatedAt time.Time,
) error {
	_, err := s.conversations.UpdateOne(ctx, bson.M{"_id": conversationID}, bson.M{
		"$set": bson.M{
			"activeTurnId": activeTurnID,
			"lastTurnId":   lastTurnID,
			"updatedAt":    updatedAt.UTC(),
		},
	})
	return err
}

func (s *MongoConversationRunStore) InsertTurn(
	ctx context.Context,
	turn assistant.AssistantTurn,
) (assistant.AssistantTurn, bool, error) {
	if _, err := s.runs.InsertOne(ctx, turn); err != nil {
		if mongo.IsDuplicateKeyError(err) && turn.ClientRequestID != "" {
			var existing assistant.AssistantTurn
			findErr := s.runs.FindOne(ctx, bson.M{
				"userId":          turn.UserID,
				"conversationId":  turn.ConversationID,
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

func (s *MongoConversationRunStore) GetTurn(
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

// CompleteTurn 以内部 CAS 把 running turn 推进到终态；已终态时幂等返回存量。
func (s *MongoConversationRunStore) CompleteTurn(
	ctx context.Context,
	turn assistant.AssistantTurn,
) (assistant.AssistantTurn, error) {
	update := bson.M{"$set": bson.M{
		"status":      turn.Status,
		"answerText":  turn.AnswerText,
		"skillId":     turn.SkillID,
		"domainId":    turn.DomainID,
		"streamState": turn.StreamState,
		"failure":     turn.Failure,
		"completedAt": turn.CompletedAt,
	}}
	result, err := s.runs.UpdateOne(
		ctx,
		bson.M{"_id": turn.TurnID, "status": "running"},
		update,
	)
	if err != nil {
		return assistant.AssistantTurn{}, err
	}
	if result.MatchedCount == 1 {
		return turn, nil
	}
	stored, found, err := s.GetTurn(ctx, turn.TurnID)
	if err != nil {
		return assistant.AssistantTurn{}, err
	}
	if !found {
		return assistant.AssistantTurn{}, mongo.ErrNoDocuments
	}
	if stored.Status == turn.Status && turn.StreamState.LastSeq > stored.StreamState.LastSeq {
		_, updateErr := s.runs.UpdateOne(
			ctx,
			bson.M{
				"_id":    turn.TurnID,
				"status": turn.Status,
				"$or": bson.A{
					bson.M{"streamState.lastSeq": bson.M{"$lt": turn.StreamState.LastSeq}},
					bson.M{"streamState.lastSeq": bson.M{"$exists": false}},
				},
			},
			bson.M{"$set": bson.M{"streamState": turn.StreamState}},
		)
		if updateErr != nil {
			return assistant.AssistantTurn{}, updateErr
		}
		stored.StreamState = turn.StreamState
	}
	return stored, nil
}

func (s *MongoConversationRunStore) ListCompletedTurns(
	ctx context.Context,
	userID string,
	conversationID string,
	limit int,
) ([]assistant.AssistantTurn, error) {
	if limit <= 0 || limit > 50 {
		limit = 6
	}
	cursor, err := s.runs.Find(ctx, bson.M{
		"conversationId": conversationID,
		"userId":         userID,
		"status":         "completed",
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

// ListConversations 以 updatedAt desc + _id desc 的 keyset 分页返回 owner 会话。
func (s *MongoConversationRunStore) ListConversations(
	ctx context.Context,
	userID string,
	limit int,
	cursor string,
) ([]assistant.AssistantConversation, string, error) {
	limit = clampPageLimit(limit)
	filter := bson.M{"userId": userID}
	if cursor != "" {
		at, id, ok := decodeKeysetCursor(cursor)
		if !ok {
			return nil, "", fmt.Errorf("invalid conversations cursor")
		}
		filter["$or"] = bson.A{
			bson.M{"updatedAt": bson.M{"$lt": at}},
			bson.M{"updatedAt": at, "_id": bson.M{"$lt": id}},
		}
	}
	findCursor, err := s.conversations.Find(ctx, filter, options.Find().
		SetSort(bson.D{{Key: "updatedAt", Value: -1}, {Key: "_id", Value: -1}}).
		SetLimit(int64(limit+1)))
	if err != nil {
		return nil, "", err
	}
	defer findCursor.Close(ctx)
	items := []assistant.AssistantConversation{}
	if err := findCursor.All(ctx, &items); err != nil {
		return nil, "", err
	}
	nextCursor := ""
	if len(items) > limit {
		items = items[:limit]
		last := items[len(items)-1]
		nextCursor = encodeKeysetCursor(last.UpdatedAt, last.ConversationID)
	}
	return items, nextCursor, nil
}

// ListTurns 以 createdAt desc + _id desc 的 keyset 分页返回会话终态轮次。
func (s *MongoConversationRunStore) ListTurns(
	ctx context.Context,
	userID string,
	conversationID string,
	limit int,
	cursor string,
) ([]assistant.AssistantTurn, string, error) {
	limit = clampPageLimit(limit)
	filter := bson.M{
		"conversationId": conversationID,
		"userId":         userID,
		"status":         bson.M{"$in": terminalTurnStatuses},
	}
	if cursor != "" {
		at, id, ok := decodeKeysetCursor(cursor)
		if !ok {
			return nil, "", fmt.Errorf("invalid turns cursor")
		}
		filter["$or"] = bson.A{
			bson.M{"createdAt": bson.M{"$lt": at}},
			bson.M{"createdAt": at, "_id": bson.M{"$lt": id}},
		}
	}
	findCursor, err := s.runs.Find(ctx, filter, options.Find().
		SetSort(bson.D{{Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}}).
		SetLimit(int64(limit+1)))
	if err != nil {
		return nil, "", err
	}
	defer findCursor.Close(ctx)
	items := []assistant.AssistantTurn{}
	if err := findCursor.All(ctx, &items); err != nil {
		return nil, "", err
	}
	nextCursor := ""
	if len(items) > limit {
		items = items[:limit]
		last := items[len(items)-1]
		nextCursor = encodeKeysetCursor(last.CreatedAt, last.TurnID)
	}
	return items, nextCursor, nil
}

func (s *MongoConversationRunStore) AppendRunEvent(
	ctx context.Context,
	runID string,
	envelope streaming.Envelope,
) error {
	envelope = envelope.Normalized()
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
			return nil
		}
		return err
	}
	return nil
}

func (s *MongoConversationRunStore) ListRunEvents(
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
	return events, nil
}

// MemoryConversationRunStore 仅供测试装配；生产启动经
// TestRuntimeDependenciesRejectMissingOrMemoryStorage 拒绝 memory 变体。
type MemoryConversationRunStore struct {
	mu            sync.RWMutex
	conversations map[string]assistant.AssistantConversation
	turns         map[string]assistant.AssistantTurn
	runEvents     map[string][]streaming.Envelope
}

func NewMemoryConversationRunStore() *MemoryConversationRunStore {
	return &MemoryConversationRunStore{
		conversations: map[string]assistant.AssistantConversation{},
		turns:         map[string]assistant.AssistantTurn{},
		runEvents:     map[string][]streaming.Envelope{},
	}
}

func (s *MemoryConversationRunStore) InsertConversation(
	_ context.Context,
	conversation assistant.AssistantConversation,
) (assistant.AssistantConversation, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if conversation.ClientRequestID != "" {
		for _, existing := range s.conversations {
			if existing.UserID == conversation.UserID &&
				existing.ClientRequestID == conversation.ClientRequestID {
				return existing, true, nil
			}
		}
	}
	s.conversations[conversation.ConversationID] = conversation
	return conversation, false, nil
}

func (s *MemoryConversationRunStore) GetConversation(
	_ context.Context,
	conversationID string,
) (assistant.AssistantConversation, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	conversation, ok := s.conversations[strings.TrimSpace(conversationID)]
	return conversation, ok, nil
}

func (s *MemoryConversationRunStore) OwnedConversationExists(
	_ context.Context,
	userID string,
	conversationID string,
) (bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	conversation, ok := s.conversations[strings.TrimSpace(conversationID)]
	return ok && conversation.UserID == strings.TrimSpace(userID), nil
}

func (s *MemoryConversationRunStore) UpdateConversationTurnPointer(
	_ context.Context,
	conversationID string,
	activeTurnID string,
	lastTurnID string,
	updatedAt time.Time,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	conversation, ok := s.conversations[conversationID]
	if !ok {
		return nil
	}
	conversation.ActiveTurnID = activeTurnID
	conversation.LastTurnID = lastTurnID
	conversation.UpdatedAt = updatedAt.UTC()
	s.conversations[conversationID] = conversation
	return nil
}

func (s *MemoryConversationRunStore) InsertTurn(
	_ context.Context,
	turn assistant.AssistantTurn,
) (assistant.AssistantTurn, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if turn.ClientRequestID != "" {
		for _, existing := range s.turns {
			if existing.UserID == turn.UserID &&
				existing.ConversationID == turn.ConversationID &&
				existing.ClientRequestID == turn.ClientRequestID {
				return existing, true, nil
			}
		}
	}
	s.turns[turn.TurnID] = turn
	return turn, false, nil
}

func (s *MemoryConversationRunStore) GetTurn(
	_ context.Context,
	turnID string,
) (assistant.AssistantTurn, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	turn, ok := s.turns[strings.TrimSpace(turnID)]
	return turn, ok, nil
}

func (s *MemoryConversationRunStore) CompleteTurn(
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
			s.turns[turn.TurnID] = stored
		}
		return stored, nil
	}
	s.turns[turn.TurnID] = turn
	return turn, nil
}

func (s *MemoryConversationRunStore) ListCompletedTurns(
	_ context.Context,
	userID string,
	conversationID string,
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
			turn.ConversationID == conversationID &&
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

func (s *MemoryConversationRunStore) ListConversations(
	_ context.Context,
	userID string,
	limit int,
	cursor string,
) ([]assistant.AssistantConversation, string, error) {
	limit = clampPageLimit(limit)
	s.mu.RLock()
	defer s.mu.RUnlock()
	items := []assistant.AssistantConversation{}
	for _, conversation := range s.conversations {
		if conversation.UserID == userID {
			items = append(items, conversation)
		}
	}
	sort.Slice(items, func(i, j int) bool {
		if !items[i].UpdatedAt.Equal(items[j].UpdatedAt) {
			return items[i].UpdatedAt.After(items[j].UpdatedAt)
		}
		return items[i].ConversationID > items[j].ConversationID
	})
	if cursor != "" {
		at, id, ok := decodeKeysetCursor(cursor)
		if !ok {
			return nil, "", fmt.Errorf("invalid conversations cursor")
		}
		filtered := items[:0:0]
		for _, item := range items {
			if item.UpdatedAt.Before(at) ||
				(item.UpdatedAt.Equal(at) && item.ConversationID < id) {
				filtered = append(filtered, item)
			}
		}
		items = filtered
	}
	nextCursor := ""
	if len(items) > limit {
		items = items[:limit]
		last := items[len(items)-1]
		nextCursor = encodeKeysetCursor(last.UpdatedAt, last.ConversationID)
	}
	return items, nextCursor, nil
}

func (s *MemoryConversationRunStore) ListTurns(
	_ context.Context,
	userID string,
	conversationID string,
	limit int,
	cursor string,
) ([]assistant.AssistantTurn, string, error) {
	limit = clampPageLimit(limit)
	terminal := map[string]struct{}{}
	for _, status := range terminalTurnStatuses {
		terminal[status] = struct{}{}
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	items := []assistant.AssistantTurn{}
	for _, turn := range s.turns {
		if turn.UserID != userID || turn.ConversationID != conversationID {
			continue
		}
		if _, ok := terminal[turn.Status]; !ok {
			continue
		}
		items = append(items, turn)
	}
	sort.Slice(items, func(i, j int) bool {
		if !items[i].CreatedAt.Equal(items[j].CreatedAt) {
			return items[i].CreatedAt.After(items[j].CreatedAt)
		}
		return items[i].TurnID > items[j].TurnID
	})
	if cursor != "" {
		at, id, ok := decodeKeysetCursor(cursor)
		if !ok {
			return nil, "", fmt.Errorf("invalid turns cursor")
		}
		filtered := items[:0:0]
		for _, item := range items {
			if item.CreatedAt.Before(at) ||
				(item.CreatedAt.Equal(at) && item.TurnID < id) {
				filtered = append(filtered, item)
			}
		}
		items = filtered
	}
	nextCursor := ""
	if len(items) > limit {
		items = items[:limit]
		last := items[len(items)-1]
		nextCursor = encodeKeysetCursor(last.CreatedAt, last.TurnID)
	}
	return items, nextCursor, nil
}

func (s *MemoryConversationRunStore) AppendRunEvent(
	_ context.Context,
	runID string,
	envelope streaming.Envelope,
) error {
	envelope = envelope.Normalized()
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, existing := range s.runEvents[runID] {
		if existing.Seq == envelope.Seq {
			return nil
		}
	}
	s.runEvents[runID] = append(s.runEvents[runID], envelope)
	sort.Slice(s.runEvents[runID], func(i, j int) bool {
		return s.runEvents[runID][i].Seq < s.runEvents[runID][j].Seq
	})
	return nil
}

func (s *MemoryConversationRunStore) ListRunEvents(
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
	return events, nil
}
