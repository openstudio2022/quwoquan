// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/recent-search-sync-and-voice-asr/spec.md#gwt-001
// readiness_case: list-recent-searches-local
// readiness_case: upsert-recent-search-local
// readiness_case: delete-recent-search-local
// readiness_case: clear-recent-searches-local
package local_contract

import (
	"context"
	"strings"
	"sync"
	"testing"
	"time"

	recentsearch "quwoquan_service/services/search-service/internal/search/recent_search_state/application"
	"quwoquan_service/services/search-service/internal/search/recent_search_state/domain/model"
	"quwoquan_service/services/search-service/internal/search/recent_search_state/domain/ports"
)

// memoryStore 是 ports.Store 的合同级内存实现：CAS、receipt 语义与 Mongo 实现同构。
type memoryStore struct {
	mu       sync.Mutex
	states   map[string]model.State
	receipts map[string]ports.Receipt
}

func newMemoryStore() *memoryStore {
	return &memoryStore{
		states:   map[string]model.State{},
		receipts: map[string]ports.Receipt{},
	}
}

func (s *memoryStore) Load(_ context.Context, personaID, scope string) (model.State, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	state, ok := s.states[model.StateID(personaID, scope)]
	return state, ok, nil
}

func (s *memoryStore) ListByPersona(_ context.Context, personaID string) ([]model.State, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	var out []model.State
	for _, state := range s.states {
		if state.PersonaID == strings.TrimSpace(personaID) {
			out = append(out, state)
		}
	}
	return out, nil
}

func (s *memoryStore) FindEntryOwner(_ context.Context, personaID, entryID string) (model.State, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, state := range s.states {
		if state.PersonaID != strings.TrimSpace(personaID) {
			continue
		}
		for _, entry := range state.Entries {
			if entry.EntryID == strings.TrimSpace(entryID) {
				return state, true, nil
			}
		}
	}
	return model.State{}, false, nil
}

func (s *memoryStore) FindReceipt(_ context.Context, receiptKey, commandDigest string) (ports.Receipt, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receipt, ok := s.receipts[receiptKey]
	if !ok {
		return ports.Receipt{}, false, nil
	}
	if receipt.CommandDigest != commandDigest {
		return ports.Receipt{}, false, ports.ErrIdempotencyConflict
	}
	receipt.Replayed = true
	return receipt, true, nil
}

func (s *memoryStore) Commit(_ context.Context, commit ports.Commit) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if existing, ok := s.receipts[commit.Receipt.ReceiptKey]; ok {
		if existing.CommandDigest != commit.Receipt.CommandDigest {
			return ports.ErrIdempotencyConflict
		}
		return nil
	}
	current, exists := s.states[commit.State.ID]
	if commit.ExpectedVersion == 0 {
		if exists {
			return ports.ErrVersionConflict
		}
	} else if !exists || current.Version != commit.ExpectedVersion {
		return ports.ErrVersionConflict
	}
	s.states[commit.State.ID] = commit.State
	s.receipts[commit.Receipt.ReceiptKey] = commit.Receipt
	return nil
}

func (s *memoryStore) RecordNoopReceipt(_ context.Context, receipt ports.Receipt) (ports.Receipt, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if existing, ok := s.receipts[receipt.ReceiptKey]; ok {
		if existing.CommandDigest != receipt.CommandDigest {
			return ports.Receipt{}, ports.ErrIdempotencyConflict
		}
		existing.Replayed = true
		return existing, nil
	}
	s.receipts[receipt.ReceiptKey] = receipt
	return receipt, nil
}

func newFacade(t *testing.T) (*recentsearch.Facade, *memoryStore) {
	t.Helper()
	store := newMemoryStore()
	facade, err := recentsearch.NewFacade(store)
	if err != nil {
		t.Fatalf("new facade: %v", err)
	}
	return facade, store
}

func TestRecentSearchUpsertDedupesSemanticKeyAndBounds(t *testing.T) {
	t.Parallel()
	facade, _ := newFacade(t)
	ctx := context.Background()

	first, err := facade.Upsert(ctx, recentsearch.UpsertCommand{
		PersonaID: "persona-1", Scope: "all", Query: "  Chengdu Travel ",
		IdempotencyKey: "upsert-1",
	})
	if err != nil {
		t.Fatalf("first upsert: %v", err)
	}
	if first.Entry.EntryID == "" || first.Replayed {
		t.Fatalf("first upsert must derive server entryId: %+v", first)
	}

	// 同语义键（大小写/空白归一）重复 upsert：仍是一条，位次置顶。
	second, err := facade.Upsert(ctx, recentsearch.UpsertCommand{
		PersonaID: "persona-1", Scope: "all", Query: "chengdu travel",
		IdempotencyKey: "upsert-2",
	})
	if err != nil {
		t.Fatalf("second upsert: %v", err)
	}
	if second.Entry.EntryID != first.Entry.EntryID {
		t.Fatalf("semantic key must derive the same entryId: %q vs %q", second.Entry.EntryID, first.Entry.EntryID)
	}
	entries, err := facade.List(ctx, "persona-1", "all")
	if err != nil || len(entries) != 1 {
		t.Fatalf("semantic dedupe must keep one entry: entries=%d err=%v", len(entries), err)
	}

	// 超上限淘汰最旧。
	for i := 0; i < model.MaxEntries+3; i++ {
		if _, err := facade.Upsert(ctx, recentsearch.UpsertCommand{
			PersonaID: "persona-1", Scope: "all",
			Query:          "query-" + strings.Repeat("x", i+1),
			IdempotencyKey: "bound-" + strings.Repeat("k", i+1),
		}); err != nil {
			t.Fatalf("bound upsert %d: %v", i, err)
		}
	}
	entries, err = facade.List(ctx, "persona-1", "all")
	if err != nil || len(entries) != model.MaxEntries {
		t.Fatalf("entries must stay bounded at %d: got=%d err=%v", model.MaxEntries, len(entries), err)
	}
}

func TestRecentSearchReceiptReplayAndDigestConflict(t *testing.T) {
	t.Parallel()
	facade, _ := newFacade(t)
	ctx := context.Background()

	command := recentsearch.UpsertCommand{
		PersonaID: "persona-2", Scope: "all", Query: "replay target",
		IdempotencyKey: "same-key",
	}
	first, err := facade.Upsert(ctx, command)
	if err != nil {
		t.Fatalf("first: %v", err)
	}
	replayed, err := facade.Upsert(ctx, command)
	if err != nil {
		t.Fatalf("replay: %v", err)
	}
	if !replayed.Replayed || replayed.Entry.EntryID != first.Entry.EntryID {
		t.Fatalf("same key must replay original result: %+v", replayed)
	}

	// 相同 key 不同 payload：幂等冲突。
	_, err = facade.Upsert(ctx, recentsearch.UpsertCommand{
		PersonaID: "persona-2", Scope: "all", Query: "different payload",
		IdempotencyKey: "same-key",
	})
	if err == nil || !strings.Contains(err.Error(), "recent_idempotency_conflict") {
		t.Fatalf("same key different payload must conflict: %v", err)
	}

	// 缺 Idempotency-Key：结构化 invalid_argument。
	if _, err := facade.Upsert(ctx, recentsearch.UpsertCommand{
		PersonaID: "persona-2", Scope: "all", Query: "no key",
	}); err == nil {
		t.Fatal("missing Idempotency-Key must be rejected")
	}
}

func TestRecentSearchReceiptCarriesApplicationOwnedReplayWindow(t *testing.T) {
	t.Parallel()
	facade, store := newFacade(t)
	if _, err := facade.Upsert(context.Background(), recentsearch.UpsertCommand{
		PersonaID:      "persona-receipt-window",
		Scope:          "all",
		Query:          "receipt window",
		IdempotencyKey: "receipt-window-1",
	}); err != nil {
		t.Fatal(err)
	}
	if len(store.receipts) != 1 {
		t.Fatalf("expected one receipt, got %d", len(store.receipts))
	}
	for _, receipt := range store.receipts {
		if got, want := receipt.ExpiresAt.Sub(receipt.CreatedAt), time.Duration(recentsearch.ReceiptTTLSeconds)*time.Second; got != want || want != 24*time.Hour {
			t.Fatalf("receipt replay window drift: got=%s want=%s", got, want)
		}
	}
}

func TestRecentSearchDeleteAndClearNoopReceipt(t *testing.T) {
	t.Parallel()
	facade, _ := newFacade(t)
	ctx := context.Background()

	created, err := facade.Upsert(ctx, recentsearch.UpsertCommand{
		PersonaID: "persona-3", Scope: "all", Query: "to delete",
		IdempotencyKey: "create",
	})
	if err != nil {
		t.Fatalf("create: %v", err)
	}

	// 删除不存在的 entry：no-op receipt，首次不 replayed，重放 replayed。
	missing := recentsearch.DeleteCommand{
		PersonaID: "persona-3", EntryID: "recent_ffffffffffffffff",
		IdempotencyKey: "delete-missing",
	}
	noop, err := facade.Delete(ctx, missing)
	if err != nil || noop.Replayed {
		t.Fatalf("missing delete must persist first no-op receipt: %+v err=%v", noop, err)
	}
	replayedNoop, err := facade.Delete(ctx, missing)
	if err != nil || !replayedNoop.Replayed {
		t.Fatalf("missing delete retry must replay no-op: %+v err=%v", replayedNoop, err)
	}

	// 真实删除后列表为空；重复 clear no-op 安全。
	if _, err := facade.Delete(ctx, recentsearch.DeleteCommand{
		PersonaID: "persona-3", EntryID: created.Entry.EntryID,
		IdempotencyKey: "delete-real",
	}); err != nil {
		t.Fatalf("real delete: %v", err)
	}
	entries, err := facade.List(ctx, "persona-3", "all")
	if err != nil || len(entries) != 0 {
		t.Fatalf("entries must be empty after delete: %d err=%v", len(entries), err)
	}
	clear := recentsearch.ClearCommand{
		PersonaID: "persona-3", Scope: "all", IdempotencyKey: "clear-1",
	}
	if _, err := facade.Clear(ctx, clear); err != nil {
		t.Fatalf("clear empty state must be no-op safe: %v", err)
	}
	again, err := facade.Clear(ctx, clear)
	if err != nil || !again.Replayed {
		t.Fatalf("clear retry must replay: %+v err=%v", again, err)
	}
}

func TestRecentSearchOwnerIsolationAndServerDerivedIdentity(t *testing.T) {
	t.Parallel()
	facade, _ := newFacade(t)
	ctx := context.Background()

	if _, err := facade.Upsert(ctx, recentsearch.UpsertCommand{
		PersonaID: "persona-a", Scope: "all", Query: "mine",
		IdempotencyKey: "a-1",
	}); err != nil {
		t.Fatalf("persona-a upsert: %v", err)
	}
	entries, err := facade.List(ctx, "persona-b", "")
	if err != nil || len(entries) != 0 {
		t.Fatalf("persona-b must not read persona-a state: %d err=%v", len(entries), err)
	}
	if _, err := facade.List(ctx, "", ""); err == nil {
		t.Fatal("missing persona must be unauthorized")
	}

	// entryId 由服务端从语义键派生：跨调用稳定（替代客户端 hashCode）。
	want := model.DeriveEntryID("all", "", "mine")
	got, err := facade.List(ctx, "persona-a", "all")
	if err != nil || len(got) != 1 || got[0].EntryID != want {
		t.Fatalf("server-derived entryId must be stable: got=%+v want=%s err=%v", got, want, err)
	}
}

func TestRecentSearchModelClock(t *testing.T) {
	t.Parallel()
	// Upsert 置顶语义依赖单调 now：同 facade 内先后两条的 UpdatedAt 有序。
	state := model.NewState("p", "all", time.Now())
	if _, changed, err := state.Upsert("first", "", time.Now()); err != nil || !changed {
		t.Fatalf("first upsert: changed=%v err=%v", changed, err)
	}
	time.Sleep(2 * time.Millisecond)
	if _, changed, err := state.Upsert("second", "", time.Now()); err != nil || !changed {
		t.Fatalf("second upsert: changed=%v err=%v", changed, err)
	}
	if len(state.Entries) != 2 || state.Entries[0].Query != "second" {
		t.Fatalf("most recent entry must lead: %+v", state.Entries)
	}
	if state.Version != 2 {
		t.Fatalf("version must advance per mutation: %d", state.Version)
	}
}
