package application

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"sync"
	"time"
)

type Store interface {
	UpsertIfNewer(context.Context, Item, string, int64, string) (bool, error)
	TombstoneIfNewer(context.Context, Identity, string, int64) (bool, error)
	TombstoneConversationIfNewer(context.Context, string, string, int64) (int64, error)
	List(context.Context, string, int, string) (Page, error)
	CompleteRebuild(context.Context, string) (int64, error)
}

type CheckpointStore interface {
	Load(context.Context, string) (string, error)
	Save(context.Context, string, string) error
}

type EventSource interface {
	ReadAfter(context.Context, string, int) ([]Event, error)
}

type SnapshotSource interface {
	Load(context.Context, Identity) (Item, bool, error)
	ListIdentities(context.Context, string, int) ([]Identity, string, error)
}

type MembershipReader interface {
	ListPersonaIDs(context.Context, string) ([]string, error)
}

type StateAdvancer interface {
	AdvanceUnread(context.Context, Identity, int64, int, int, time.Time) error
}

// ChatInboxViewProjector owns the durable, replay-safe projection lifecycle for
// chat.chat_inbox_view.  The explicit object-qualified name is also the
// metadata lifecycle facet; transport composition must not invent a second
// projector identity.
type ChatInboxViewProjector struct {
	store       Store
	checkpoints CheckpointStore
	snapshots   SnapshotSource
	members     MembershipReader
	states      StateAdvancer
	sources     map[string]EventSource

	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

func NewProjector(
	store Store,
	checkpoints CheckpointStore,
	snapshots SnapshotSource,
	members MembershipReader,
	states StateAdvancer,
	sources map[string]EventSource,
) *ChatInboxViewProjector {
	return &ChatInboxViewProjector{
		store: store, checkpoints: checkpoints, snapshots: snapshots,
		members: members, states: states, sources: sources,
	}
}

func (projector *ChatInboxViewProjector) Drain(ctx context.Context, limit int) (int, error) {
	if projector == nil || projector.store == nil || projector.checkpoints == nil ||
		projector.snapshots == nil || projector.members == nil || projector.states == nil ||
		len(projector.sources) == 0 {
		return 0, errors.New("ChatInboxView projector is not fully configured")
	}
	processed := 0
	for _, sourceName := range []string{"message", "conversation", "membership", "user_state"} {
		source := projector.sources[sourceName]
		if source == nil {
			continue
		}
		count, err := projector.drainSource(ctx, sourceName, source, limit)
		processed += count
		if err != nil {
			projector.recordFailure(err)
			return processed, err
		}
	}
	projector.recordSuccess()
	return processed, nil
}

func (projector *ChatInboxViewProjector) drainSource(
	ctx context.Context,
	sourceName string,
	source EventSource,
	limit int,
) (int, error) {
	consumer := "chat-inbox-view-" + sourceName
	checkpoint, err := projector.checkpoints.Load(ctx, consumer)
	if err != nil {
		return 0, fmt.Errorf("load %s checkpoint: %w", consumer, err)
	}
	events, err := source.ReadAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, fmt.Errorf("read %s source: %w", sourceName, err)
	}
	for index, event := range events {
		sequence, err := parseCheckpoint(event.Checkpoint)
		if err != nil {
			return index, fmt.Errorf("%s event %s: %w", sourceName, event.ID, err)
		}
		if err := projector.apply(ctx, sourceName, sequence, event); err != nil {
			return index, fmt.Errorf("apply %s event %s: %w", sourceName, event.ID, err)
		}
		if err := projector.checkpoints.Save(ctx, consumer, event.Checkpoint); err != nil {
			return index, fmt.Errorf("save %s checkpoint: %w", consumer, err)
		}
	}
	return len(events), nil
}

func (projector *ChatInboxViewProjector) apply(
	ctx context.Context,
	sourceName string,
	sequence int64,
	event Event,
) error {
	conversationID := strings.TrimSpace(event.ConversationID)
	if conversationID == "" {
		return errors.New("conversationId is required")
	}
	switch sourceName {
	case "message":
		return projector.applyMessage(ctx, sequence, event)
	case "membership":
		userID := stringPayload(event.Payload["userId"])
		if userID == "" {
			userID = strings.TrimSpace(event.ActorID)
		}
		if userID == "" {
			return errors.New("membership event userId is required")
		}
		return projector.refresh(ctx, Identity{UserID: userID, ConversationID: conversationID}, sourceName, sequence, "")
	case "user_state":
		userID := stringPayload(event.Payload["userId"])
		if userID == "" {
			userID = strings.TrimSpace(event.ActorID)
		}
		return projector.refresh(ctx, Identity{UserID: userID, ConversationID: conversationID}, sourceName, sequence, "")
	case "conversation":
		if strings.Contains(strings.ToLower(event.Type), "dissolved") {
			_, err := projector.store.TombstoneConversationIfNewer(ctx, conversationID, sourceName, sequence)
			return err
		}
		personaIDs, err := projector.members.ListPersonaIDs(ctx, conversationID)
		if err != nil {
			return err
		}
		for _, userID := range personaIDs {
			if err := projector.refresh(ctx, Identity{UserID: userID, ConversationID: conversationID}, sourceName, sequence, ""); err != nil {
				return err
			}
		}
		return nil
	default:
		return fmt.Errorf("unsupported source %q", sourceName)
	}
}

func (projector *ChatInboxViewProjector) applyMessage(ctx context.Context, sequence int64, event Event) error {
	eventSeq := int64Payload(event.Payload["seq"])
	if eventSeq <= 0 {
		return errors.New("message seq must be positive")
	}
	conversationID := strings.TrimSpace(event.ConversationID)
	if event.Type == "MessageRecalled" {
		personaIDs, err := projector.members.ListPersonaIDs(ctx, conversationID)
		if err != nil {
			return err
		}
		for _, userID := range personaIDs {
			if err := projector.refresh(
				ctx,
				Identity{UserID: userID, ConversationID: conversationID},
				"message",
				sequence,
				"",
			); err != nil {
				return err
			}
		}
		return nil
	}
	if event.Type == "AssistantMentioned" {
		// message 聚合的助手可靠消费事件：消费者是 assistant-service，
		// 不影响 inbox 投影，跳过而不是中断整个 drain。
		return nil
	}
	if event.Type != "MessageSent" {
		return fmt.Errorf("unsupported message event %q", event.Type)
	}
	senderID := strings.TrimSpace(event.ActorID)
	if senderID == "" {
		senderID = stringPayload(event.Payload["senderId"])
	}
	occurredAt := time.Now().UTC()
	if value, ok := event.Payload["timestamp"].(time.Time); ok {
		occurredAt = value.UTC()
	}
	mentions, mentionAll := mentionSet(event.Payload["mentions"])
	personaIDs, err := projector.members.ListPersonaIDs(ctx, conversationID)
	if err != nil {
		return err
	}
	for _, userID := range personaIDs {
		unreadDelta := 1
		if userID == senderID {
			unreadDelta = 0
		}
		mentionDelta := 0
		if _, mentioned := mentions[userID]; (mentioned || mentionAll) && userID != senderID {
			mentionDelta = 1
		}
		identity := Identity{UserID: userID, ConversationID: conversationID}
		if err := projector.states.AdvanceUnread(
			ctx, identity, eventSeq, unreadDelta, mentionDelta, occurredAt,
		); err != nil {
			return err
		}
		if err := projector.refresh(ctx, identity, "message", sequence, ""); err != nil {
			return err
		}
	}
	return nil
}

func (projector *ChatInboxViewProjector) refresh(
	ctx context.Context,
	identity Identity,
	source string,
	sequence int64,
	rebuildRunID string,
) error {
	if strings.TrimSpace(identity.UserID) == "" || strings.TrimSpace(identity.ConversationID) == "" {
		return errors.New("ChatInboxView identity is required")
	}
	item, visible, err := projector.snapshots.Load(ctx, identity)
	if err != nil {
		return err
	}
	if !visible {
		_, err = projector.store.TombstoneIfNewer(ctx, identity, source, sequence)
		return err
	}
	_, err = projector.store.UpsertIfNewer(ctx, item, source, sequence, rebuildRunID)
	return err
}

func (projector *ChatInboxViewProjector) Rebuild(ctx context.Context, runID string, batchSize int) (int, error) {
	runID = strings.TrimSpace(runID)
	if runID == "" {
		return 0, errors.New("ChatInboxView rebuild runId is required")
	}
	if batchSize <= 0 {
		batchSize = 500
	}
	afterID := ""
	projected := 0
	sequence := int64(1)
	for {
		identities, next, err := projector.snapshots.ListIdentities(ctx, afterID, batchSize)
		if err != nil {
			return projected, err
		}
		for _, identity := range identities {
			if err := projector.refresh(ctx, identity, "rebuild", sequence, runID); err != nil {
				return projected, err
			}
			sequence++
			projected++
		}
		if next == "" {
			break
		}
		afterID = next
	}
	if _, err := projector.store.CompleteRebuild(ctx, runID); err != nil {
		return projected, err
	}
	return projected, nil
}

func (projector *ChatInboxViewProjector) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		interval = 200 * time.Millisecond
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		_, _ = projector.Drain(ctx, 100)
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

func (projector *ChatInboxViewProjector) Healthy(maxStaleness time.Duration) error {
	if maxStaleness <= 0 {
		maxStaleness = 5 * time.Second
	}
	projector.mu.RLock()
	defer projector.mu.RUnlock()
	if projector.lastSuccess.IsZero() {
		return errors.New("ChatInboxView projector has not completed a scan")
	}
	if projector.lastFailure != nil {
		return projector.lastFailure
	}
	if time.Since(projector.lastSuccess) > maxStaleness {
		return errors.New("ChatInboxView projector heartbeat is stale")
	}
	return nil
}

func (projector *ChatInboxViewProjector) recordSuccess() {
	projector.mu.Lock()
	defer projector.mu.Unlock()
	projector.lastSuccess = time.Now().UTC()
	projector.lastFailure = nil
}

func (projector *ChatInboxViewProjector) recordFailure(err error) {
	projector.mu.Lock()
	defer projector.mu.Unlock()
	projector.lastFailure = err
}

func parseCheckpoint(raw string) (int64, error) {
	checkpoint, err := strconv.ParseInt(strings.TrimSpace(raw), 10, 64)
	if err != nil || checkpoint <= 0 {
		return 0, errors.New("positive numeric checkpoint is required")
	}
	return checkpoint, nil
}

func stringPayload(value any) string {
	result, _ := value.(string)
	return strings.TrimSpace(result)
}

func int64Payload(value any) int64 {
	switch typed := value.(type) {
	case int:
		return int64(typed)
	case int32:
		return int64(typed)
	case int64:
		return typed
	case float64:
		return int64(typed)
	default:
		return 0
	}
}

func mentionSet(value any) (map[string]struct{}, bool) {
	mentions := map[string]struct{}{}
	mentionAll := false
	appendMention := func(raw string) {
		id := strings.TrimSpace(raw)
		if id == "__all__" {
			mentionAll = true
		} else if id != "" {
			mentions[id] = struct{}{}
		}
	}
	switch typed := value.(type) {
	case []string:
		for _, id := range typed {
			appendMention(id)
		}
	case []any:
		for _, item := range typed {
			if id, ok := item.(string); ok {
				appendMention(id)
			}
		}
	}
	return mentions, mentionAll
}
