// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-003
// readiness_case: list-inbox-local
// readiness_case: project-chat-inbox-local
package local_contract

import (
	"context"
	"testing"
	"time"

	inboxapp "quwoquan_service/services/chat-service/internal/chat/chat_inbox_view/application"
)

type inboxMemoryStore struct {
	upserts      int
	tombstones   int
	completed    string
	listedUser   string
	listedLimit  int
	listedCursor string
	page         inboxapp.Page
}

func (store *inboxMemoryStore) UpsertIfNewer(_ context.Context, _ inboxapp.Item, _ string, _ int64, _ string) (bool, error) {
	store.upserts++
	return true, nil
}
func (store *inboxMemoryStore) TombstoneIfNewer(_ context.Context, _ inboxapp.Identity, _ string, _ int64) (bool, error) {
	store.tombstones++
	return true, nil
}
func (store *inboxMemoryStore) TombstoneConversationIfNewer(context.Context, string, string, int64) (int64, error) {
	store.tombstones++
	return 1, nil
}
func (store *inboxMemoryStore) List(_ context.Context, userID string, limit int, cursor string) (inboxapp.Page, error) {
	store.listedUser = userID
	store.listedLimit = limit
	store.listedCursor = cursor
	return store.page, nil
}
func (store *inboxMemoryStore) CompleteRebuild(_ context.Context, runID string) (int64, error) {
	store.completed = runID
	return 0, nil
}

type inboxMemoryCheckpoints map[string]string

func (checkpoints inboxMemoryCheckpoints) Load(_ context.Context, consumer string) (string, error) {
	return checkpoints[consumer], nil
}
func (checkpoints inboxMemoryCheckpoints) Save(_ context.Context, consumer, checkpoint string) error {
	checkpoints[consumer] = checkpoint
	return nil
}

type inboxEventSource struct{ events []inboxapp.Event }

func (source inboxEventSource) ReadAfter(_ context.Context, checkpoint string, _ int) ([]inboxapp.Event, error) {
	if checkpoint != "" {
		return nil, nil
	}
	return source.events, nil
}

type inboxSnapshots struct {
	item       inboxapp.Item
	visible    bool
	identities []inboxapp.Identity
}

func (source *inboxSnapshots) Load(_ context.Context, identity inboxapp.Identity) (inboxapp.Item, bool, error) {
	item := source.item
	item.UserID, item.ConversationID = identity.UserID, identity.ConversationID
	return item, source.visible, nil
}
func (source *inboxSnapshots) ListIdentities(_ context.Context, afterID string, _ int) ([]inboxapp.Identity, string, error) {
	if afterID != "" {
		return nil, "", nil
	}
	return source.identities, "", nil
}

type inboxMembers []string

func (members inboxMembers) ListPersonaIDs(context.Context, string) ([]string, error) {
	return append([]string(nil), members...), nil
}

type inboxStateAdvancer struct{ calls int }

func (advancer *inboxStateAdvancer) AdvanceUnread(context.Context, inboxapp.Identity, int64, int, int, time.Time) error {
	advancer.calls++
	return nil
}

func TestChatInboxViewProjectorOwnsReplayTombstoneAndRebuildLifecycle(t *testing.T) {
	store := &inboxMemoryStore{}
	checkpoints := inboxMemoryCheckpoints{}
	snapshots := &inboxSnapshots{
		visible:    true,
		item:       inboxapp.Item{Type: "group", Title: "single materialized inbox"},
		identities: []inboxapp.Identity{{UserID: "persona-1", ConversationID: "conversation-1"}},
	}
	advancer := &inboxStateAdvancer{}
	projector := inboxapp.NewProjector(
		store, checkpoints, snapshots, inboxMembers{"persona-1"}, advancer,
		map[string]inboxapp.EventSource{
			"message": inboxEventSource{events: []inboxapp.Event{{
				ID: "event-1", Type: "MessageSent", ConversationID: "conversation-1",
				ActorID: "persona-2", Checkpoint: "1",
				Payload: map[string]any{"seq": int64(1), "timestamp": time.Now().UTC()},
			}, {
				ID: "event-2", Type: "MessageRecalled", ConversationID: "conversation-1",
				ActorID: "persona-2", Checkpoint: "2",
				Payload: map[string]any{"seq": int64(1), "recalledAt": time.Now().UTC()},
			}}},
		},
	)

	if processed, err := projector.Drain(context.Background(), 100); err != nil || processed != 2 {
		t.Fatalf("first projection failed: processed=%d err=%v", processed, err)
	}
	if processed, err := projector.Drain(context.Background(), 100); err != nil || processed != 0 {
		t.Fatalf("checkpoint replay must be a no-op: processed=%d err=%v", processed, err)
	}
	if store.upserts != 2 || advancer.calls != 1 || checkpoints["chat-inbox-view-message"] != "2" {
		t.Fatalf("single-track projection drifted: upserts=%d advances=%d checkpoint=%q", store.upserts, advancer.calls, checkpoints["chat-inbox-view-message"])
	}

	snapshots.visible = false
	if _, err := projector.Rebuild(context.Background(), "rebuild-1", 100); err != nil {
		t.Fatalf("rebuild failed: %v", err)
	}
	if store.tombstones != 1 || store.completed != "rebuild-1" {
		t.Fatalf("rebuild must tombstone missing identities: tombstones=%d completed=%q", store.tombstones, store.completed)
	}
}

func TestChatInboxViewReaderOwnsIdentityLimitAndOpaqueCursor(t *testing.T) {
	store := &inboxMemoryStore{page: inboxapp.Page{
		Items:      []inboxapp.Item{{UserID: "persona-1", ConversationID: "conversation-1"}},
		NextCursor: "opaque-next",
	}}
	reader := inboxapp.NewReader(store)
	page, err := reader.List(t.Context(), " persona-1 ", 0, "opaque-current")
	if err != nil || len(page.Items) != 1 || page.NextCursor != "opaque-next" {
		t.Fatalf("List() page=%+v err=%v", page, err)
	}
	if store.listedUser != "persona-1" || store.listedLimit != 50 || store.listedCursor != "opaque-current" {
		t.Fatalf(
			"reader arguments user=%q limit=%d cursor=%q",
			store.listedUser,
			store.listedLimit,
			store.listedCursor,
		)
	}
	if _, err := reader.List(t.Context(), "", 10, ""); err == nil {
		t.Fatal("empty persona identity must fail closed")
	}
}
