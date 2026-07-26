package local_contract

import (
	"context"
	"errors"
	. "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/application"
	"sort"
	"strings"
	"sync"
	"testing"
	"time"

	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/entity-service/generated/entity_homepage/homepage"
	reviewmodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/domain/model"
	reviewports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/domain/ports"
)

type memoryReceipt struct {
	commandName   string
	commandDigest string
	snapshot      reviewmodel.Snapshot
	expiresAt     time.Time
}

type memoryReviewStore struct {
	mu       sync.Mutex
	reviews  map[string]reviewmodel.Snapshot
	receipts map[string]memoryReceipt
	outbox   []reviewports.OutboxEvent
}

func newMemoryReviewStore() *memoryReviewStore {
	return &memoryReviewStore{
		reviews:  map[string]reviewmodel.Snapshot{},
		receipts: map[string]memoryReceipt{},
	}
}

func (s *memoryReviewStore) Load(
	_ context.Context,
	reviewID string,
) (*reviewmodel.HomepageReview, bool, error) {
	s.mu.Lock()
	snapshot, found := s.reviews[strings.TrimSpace(reviewID)]
	s.mu.Unlock()
	if !found {
		return nil, false, nil
	}
	aggregate, err := reviewmodel.Restore(snapshot)
	return aggregate, err == nil, err
}

func (s *memoryReviewStore) FindByAuthor(
	_ context.Context,
	homepageID string,
	authorPersonaID string,
) (*reviewmodel.HomepageReview, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, snapshot := range s.reviews {
		if snapshot.HomepageID == strings.TrimSpace(homepageID) &&
			snapshot.AuthorPersonaID == strings.TrimSpace(authorPersonaID) {
			aggregate, err := reviewmodel.Restore(snapshot)
			return aggregate, err == nil, err
		}
	}
	return nil, false, nil
}

func (s *memoryReviewStore) FindReceipt(
	_ context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (reviewports.CommitResult, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receipt, found := s.receipts[idempotencyKey]
	if !found {
		return reviewports.CommitResult{}, false, nil
	}
	if receipt.commandName != commandName || receipt.commandDigest != commandDigest {
		return reviewports.CommitResult{}, false,
			generated.AppErrorFromIdempotencyConflict("digest mismatch")
	}
	aggregate, err := reviewmodel.Restore(receipt.snapshot)
	if err != nil {
		return reviewports.CommitResult{}, false, err
	}
	return reviewports.CommitResult{Aggregate: aggregate, Replayed: true}, true, nil
}

func (s *memoryReviewStore) RecordNoopReceipt(
	_ context.Context,
	noop reviewports.NoopReceipt,
) (reviewports.CommitResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if receipt, found := s.receipts[noop.IdempotencyKey]; found {
		if receipt.commandName != noop.CommandName ||
			receipt.commandDigest != noop.CommandDigest {
			return reviewports.CommitResult{},
				generated.AppErrorFromIdempotencyConflict("digest mismatch")
		}
		aggregate, err := reviewmodel.Restore(receipt.snapshot)
		return reviewports.CommitResult{Aggregate: aggregate, Replayed: true}, err
	}
	snapshot := noop.Aggregate.Snapshot()
	s.receipts[noop.IdempotencyKey] = memoryReceipt{
		commandName:   noop.CommandName,
		commandDigest: noop.CommandDigest,
		snapshot:      snapshot,
		expiresAt:     noop.ReceiptExpiresAt,
	}
	aggregate, err := reviewmodel.Restore(snapshot)
	return reviewports.CommitResult{Aggregate: aggregate}, err
}

func (s *memoryReviewStore) Commit(
	_ context.Context,
	commit reviewports.Commit,
) (reviewports.CommitResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if receipt, found := s.receipts[commit.IdempotencyKey]; found {
		if receipt.commandName != commit.CommandName ||
			receipt.commandDigest != commit.CommandDigest {
			return reviewports.CommitResult{},
				generated.AppErrorFromIdempotencyConflict("digest mismatch")
		}
		aggregate, err := reviewmodel.Restore(receipt.snapshot)
		return reviewports.CommitResult{Aggregate: aggregate, Replayed: true}, err
	}
	snapshot := commit.Aggregate.Snapshot()
	current, exists := s.reviews[snapshot.ID]
	if commit.ExpectedVersion == 0 {
		if exists {
			return reviewports.CommitResult{},
				generated.AppErrorFromVersionConflict("review already exists")
		}
	} else if !exists || current.Version != commit.ExpectedVersion {
		return reviewports.CommitResult{},
			generated.AppErrorFromVersionConflict("review version changed")
	}
	s.reviews[snapshot.ID] = snapshot
	s.receipts[commit.IdempotencyKey] = memoryReceipt{
		commandName:   commit.CommandName,
		commandDigest: commit.CommandDigest,
		snapshot:      snapshot,
		expiresAt:     commit.ReceiptExpiresAt,
	}
	s.outbox = append(s.outbox, commit.Events...)
	aggregate, err := reviewmodel.Restore(snapshot)
	return reviewports.CommitResult{Aggregate: aggregate}, err
}

func (s *memoryReviewStore) ListByHomepage(
	_ context.Context,
	homepageID string,
	request reviewports.PageRequest,
) (reviewports.Page, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	items := make([]reviewmodel.Snapshot, 0)
	for _, snapshot := range s.reviews {
		if snapshot.HomepageID == strings.TrimSpace(homepageID) &&
			snapshot.Status == reviewmodel.StatusActive {
			items = append(items, snapshot)
		}
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i].CreatedAt.After(items[j].CreatedAt)
	})
	limit := request.Limit
	if limit <= 0 {
		limit = 20
	}
	if len(items) > limit {
		items = items[:limit]
	}
	return reviewports.Page{Items: items}, nil
}

type staticHomepageGate struct {
	statuses map[string]string
}

func (g staticHomepageGate) FindHomepageStatus(
	_ context.Context,
	homepageID string,
) (string, bool, error) {
	status, found := g.statuses[strings.TrimSpace(homepageID)]
	return status, found, nil
}

func newTestFacade(t *testing.T) (*Facade, *memoryReviewStore) {
	t.Helper()
	store := newMemoryReviewStore()
	facade, err := NewFacade(DataPorts{
		Aggregate: store,
		Page:      store,
		Homepage: staticHomepageGate{statuses: map[string]string{
			"hp-published": "published",
			"hp-offline":   "offline",
		}},
	})
	if err != nil {
		t.Fatalf("new facade: %v", err)
	}
	base := time.Date(2026, 7, 19, 10, 0, 0, 0, time.UTC)
	step := 0
	facade.SetClock(func() time.Time {
		step++
		return base.Add(time.Duration(step) * time.Second)
	})
	return facade, store
}

func commandContext(key string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		OperationID:    "test",
		RequestID:      "req-1",
		IdempotencyKey: key,
		Actor:          operation.ActorContext{PersonaID: "persona-author"},
	})
}

func TestReviewCreateUpdateDeleteReviveLifecycle(t *testing.T) {
	t.Parallel()
	facade, store := newTestFacade(t)

	created, err := facade.Create(commandContext("create-1"), CreateCommand{
		HomepageID:     "hp-published",
		ActorPersonaID: "persona-author",
		Rating:         5,
		Body:           "很棒的地方",
		TagRefs:        []string{"publish/tags/scenery"},
	})
	if err != nil {
		t.Fatalf("create review: %v", err)
	}
	if created.Version != 1 || created.Status != "active" || created.Rating != 5 {
		t.Fatalf("unexpected created review: %+v", created)
	}

	replayed, err := facade.Create(commandContext("create-1"), CreateCommand{
		HomepageID:     "hp-published",
		ActorPersonaID: "persona-author",
		Rating:         5,
		Body:           "很棒的地方",
		TagRefs:        []string{"publish/tags/scenery"},
	})
	if err != nil || replayed.Version != created.Version {
		t.Fatalf("idempotent create replay mismatch: %+v err=%v", replayed, err)
	}

	updated, err := facade.Update(commandContext("update-1"), UpdateCommand{
		ReviewID:       created.ID,
		ActorPersonaID: "persona-author",
		Rating:         4,
		Body:           "还不错",
	})
	if err != nil {
		t.Fatalf("update review: %v", err)
	}
	if updated.Version != 2 || updated.Rating != 4 {
		t.Fatalf("unexpected updated review: %+v", updated)
	}

	deleted, err := facade.Delete(commandContext("delete-1"), DeleteCommand{
		ReviewID:       created.ID,
		ActorPersonaID: "persona-author",
	})
	if err != nil {
		t.Fatalf("delete review: %v", err)
	}
	if deleted.Status != "deleted" || deleted.Version != 3 {
		t.Fatalf("unexpected deleted review: %+v", deleted)
	}

	// no-op receipt：已删除后相同意图的新 key 不推进版本。
	noop, err := facade.Delete(commandContext("delete-2"), DeleteCommand{
		ReviewID:       created.ID,
		ActorPersonaID: "persona-author",
	})
	if err != nil || noop.Version != 3 {
		t.Fatalf("delete no-op mismatch: %+v err=%v", noop, err)
	}

	// 复活：再次创建复用同一聚合，版本继续推进。
	revived, err := facade.Create(commandContext("create-2"), CreateCommand{
		HomepageID:     "hp-published",
		ActorPersonaID: "persona-author",
		Rating:         3,
		Body:           "重新评价",
	})
	if err != nil {
		t.Fatalf("revive review: %v", err)
	}
	if revived.ID != created.ID || revived.Version != 4 || revived.Status != "active" {
		t.Fatalf("revive must reuse the same aggregate: %+v", revived)
	}
	if len(store.reviews) != 1 {
		t.Fatalf("author+homepage must map to exactly one document, got %d", len(store.reviews))
	}
	if len(store.outbox) != 4 {
		t.Fatalf("expected 4 outbox facts (create/update/delete/revive), got %d", len(store.outbox))
	}
}

func TestReviewAuthorOnlyAndHomepageGate(t *testing.T) {
	t.Parallel()
	facade, _ := newTestFacade(t)

	if _, err := facade.Create(commandContext("gate-offline"), CreateCommand{
		HomepageID:     "hp-offline",
		ActorPersonaID: "persona-author",
		Rating:         4,
	}); !errorsIsCode(err, generated.ErrHomepageOffline) {
		t.Fatalf("offline homepage must reject review: %v", err)
	}
	if _, err := facade.Create(commandContext("gate-missing"), CreateCommand{
		HomepageID:     "hp-missing",
		ActorPersonaID: "persona-author",
		Rating:         4,
	}); !errorsIsCode(err, generated.ErrHomepageNotFound) {
		t.Fatalf("missing homepage must reject review: %v", err)
	}

	created, err := facade.Create(commandContext("gate-create"), CreateCommand{
		HomepageID:     "hp-published",
		ActorPersonaID: "persona-author",
		Rating:         5,
	})
	if err != nil {
		t.Fatalf("create review: %v", err)
	}
	intruder := operation.WithContext(context.Background(), operation.Context{
		OperationID:    "test",
		RequestID:      "req-2",
		IdempotencyKey: "intruder-update",
		Actor:          operation.ActorContext{PersonaID: "persona-intruder"},
	})
	if _, err := facade.Update(intruder, UpdateCommand{
		ReviewID:       created.ID,
		ActorPersonaID: "persona-intruder",
		Rating:         1,
	}); !errorsIsCode(err, generated.ErrPermissionDenied) {
		t.Fatalf("non-author update must be denied: %v", err)
	}
}

func TestReviewDuplicateActiveCreateConflictsAndListFiltersDeleted(t *testing.T) {
	t.Parallel()
	facade, _ := newTestFacade(t)

	first, err := facade.Create(commandContext("dup-create"), CreateCommand{
		HomepageID:     "hp-published",
		ActorPersonaID: "persona-author",
		Rating:         5,
		Body:           "第一条",
	})
	if err != nil {
		t.Fatalf("create review: %v", err)
	}
	if _, err := facade.Create(commandContext("dup-create-2"), CreateCommand{
		HomepageID:     "hp-published",
		ActorPersonaID: "persona-author",
		Rating:         2,
		Body:           "换个内容再建",
	}); !errorsIsCode(err, generated.ErrVersionConflict) {
		t.Fatalf("duplicate active create must conflict: %v", err)
	}

	mine, err := facade.GetMine(commandContext("mine"), "hp-published", "persona-author")
	if err != nil || mine.ID != first.ID {
		t.Fatalf("get mine mismatch: %+v err=%v", mine, err)
	}

	if _, err := facade.Delete(commandContext("dup-delete"), DeleteCommand{
		ReviewID:       first.ID,
		ActorPersonaID: "persona-author",
	}); err != nil {
		t.Fatalf("delete review: %v", err)
	}
	page, err := facade.ListByHomepage(context.Background(), ListQuery{
		HomepageID: "hp-published",
	})
	if err != nil {
		t.Fatalf("list reviews: %v", err)
	}
	if len(page.Items) != 0 {
		t.Fatalf("deleted review must be hidden from list: %+v", page.Items)
	}
	// deleted 记录仍可经 GetMine 取回供复活预填。
	mineDeleted, err := facade.GetMine(commandContext("mine-2"), "hp-published", "persona-author")
	if err != nil || mineDeleted.Status != "deleted" {
		t.Fatalf("mine must return deleted review for revive prefill: %+v err=%v", mineDeleted, err)
	}
}

func errorsIsCode(err error, sentinel error) bool {
	if err == nil || sentinel == nil {
		return false
	}
	type coded interface{ Error() string }
	var appErr interface{ Error() string } = err
	_ = appErr
	return errors.Is(err, sentinel) || strings.Contains(err.Error(), sentinel.Error())
}
