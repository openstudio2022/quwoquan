package homepage_claim_request

import (
	"context"
	"encoding/json"
	"errors"
	"sort"
	"strings"
	"sync"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	claimmodel "quwoquan_service/services/entity-service/internal/domain/homepage_claim_request/model"
	claimports "quwoquan_service/services/entity-service/internal/domain/homepage_claim_request/ports"
	"quwoquan_service/services/entity-service/internal/generated"
)

type memoryReceipt struct {
	commandName   string
	commandDigest string
	snapshot      claimmodel.Snapshot
}

type memoryStore struct {
	mu                 sync.Mutex
	claims             map[string]claimmodel.Snapshot
	receipts           map[string]memoryReceipt
	outbox             []claimports.OutboxEvent
	forcedCASConflicts int
	commitCalls        int
}

func newMemoryStore() *memoryStore {
	return &memoryStore{
		claims:   make(map[string]claimmodel.Snapshot),
		receipts: make(map[string]memoryReceipt),
	}
}

func (s *memoryStore) Load(
	_ context.Context,
	claimRequestID string,
) (*claimmodel.HomepageClaimRequest, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	snapshot, found := s.claims[strings.TrimSpace(claimRequestID)]
	if !found {
		return nil, false, nil
	}
	aggregate, err := claimmodel.Restore(snapshot)
	return aggregate, err == nil, err
}

func (s *memoryStore) FindPending(
	_ context.Context,
	homepageID string,
	requesterPersonaID string,
) (*claimmodel.HomepageClaimRequest, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, snapshot := range s.claims {
		if snapshot.HomepageID == strings.TrimSpace(homepageID) &&
			snapshot.RequesterPersonaID == strings.TrimSpace(requesterPersonaID) &&
			snapshot.Status == claimmodel.StatusPendingReview {
			aggregate, err := claimmodel.Restore(snapshot)
			return aggregate, err == nil, err
		}
	}
	return nil, false, nil
}

func (s *memoryStore) ListQueue(
	_ context.Context,
	query claimports.QueueQuery,
) (claimports.QueuePage, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	items := make([]claimmodel.Snapshot, 0, len(s.claims))
	for _, snapshot := range s.claims {
		if homepageID := strings.TrimSpace(query.HomepageID); homepageID != "" &&
			snapshot.HomepageID != homepageID {
			continue
		}
		if query.Status != "" && snapshot.Status != query.Status {
			continue
		}
		items = append(items, snapshot)
	}
	sort.Slice(items, func(i, j int) bool {
		if items[i].CreatedAt.Equal(items[j].CreatedAt) {
			return items[i].ID > items[j].ID
		}
		return items[i].CreatedAt.After(items[j].CreatedAt)
	})
	limit := query.Limit
	if limit <= 0 || limit > len(items) {
		limit = len(items)
	}
	return claimports.QueuePage{Items: append([]claimmodel.Snapshot(nil), items[:limit]...)}, nil
}

func (s *memoryStore) FindReceipt(
	_ context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (claimports.CommitResult, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receipt, found := s.receipts[idempotencyKey]
	if !found {
		return claimports.CommitResult{}, false, nil
	}
	if receipt.commandName != commandName || receipt.commandDigest != commandDigest {
		return claimports.CommitResult{}, false,
			generated.AppErrorFromIdempotencyConflict("claim receipt digest mismatch")
	}
	aggregate, err := claimmodel.Restore(receipt.snapshot)
	return claimports.CommitResult{Aggregate: aggregate, Replayed: true}, err == nil, err
}

func (s *memoryStore) RecordNoopReceipt(
	_ context.Context,
	noop claimports.NoopReceipt,
) (claimports.CommitResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if receipt, found := s.receipts[noop.IdempotencyKey]; found {
		if receipt.commandName != noop.CommandName || receipt.commandDigest != noop.CommandDigest {
			return claimports.CommitResult{},
				generated.AppErrorFromIdempotencyConflict("claim receipt digest mismatch")
		}
		aggregate, err := claimmodel.Restore(receipt.snapshot)
		return claimports.CommitResult{Aggregate: aggregate, Replayed: true}, err
	}
	snapshot := noop.Aggregate.Snapshot()
	s.receipts[noop.IdempotencyKey] = memoryReceipt{
		commandName:   noop.CommandName,
		commandDigest: noop.CommandDigest,
		snapshot:      snapshot,
	}
	aggregate, err := claimmodel.Restore(snapshot)
	return claimports.CommitResult{Aggregate: aggregate}, err
}

func (s *memoryStore) Commit(
	_ context.Context,
	commit claimports.Commit,
) (claimports.CommitResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.commitCalls++
	if receipt, found := s.receipts[commit.IdempotencyKey]; found {
		if receipt.commandName != commit.CommandName || receipt.commandDigest != commit.CommandDigest {
			return claimports.CommitResult{},
				generated.AppErrorFromIdempotencyConflict("claim receipt digest mismatch")
		}
		aggregate, err := claimmodel.Restore(receipt.snapshot)
		return claimports.CommitResult{Aggregate: aggregate, Replayed: true}, err
	}
	if s.forcedCASConflicts > 0 {
		s.forcedCASConflicts--
		return claimports.CommitResult{},
			generated.AppErrorFromVersionConflict("forced claim CAS conflict")
	}
	snapshot := commit.Aggregate.Snapshot()
	current, exists := s.claims[snapshot.ID]
	if commit.ExpectedVersion == 0 {
		for _, candidate := range s.claims {
			if candidate.HomepageID == snapshot.HomepageID &&
				candidate.RequesterPersonaID == snapshot.RequesterPersonaID &&
				candidate.Status == claimmodel.StatusPendingReview {
				return claimports.CommitResult{},
					generated.AppErrorFromDuplicatePendingClaim("duplicate pending claim")
			}
		}
		if exists {
			return claimports.CommitResult{},
				generated.AppErrorFromVersionConflict("claim ID already exists")
		}
	} else if !exists || current.Version != commit.ExpectedVersion {
		return claimports.CommitResult{},
			generated.AppErrorFromVersionConflict("claim version changed")
	}
	s.claims[snapshot.ID] = snapshot
	s.receipts[commit.IdempotencyKey] = memoryReceipt{
		commandName:   commit.CommandName,
		commandDigest: commit.CommandDigest,
		snapshot:      snapshot,
	}
	s.outbox = append(s.outbox, commit.Events...)
	aggregate, err := claimmodel.Restore(snapshot)
	return claimports.CommitResult{Aggregate: aggregate}, err
}

type staticHomepageGate map[string]HomepageState

func (g staticHomepageGate) FindHomepageState(
	_ context.Context,
	homepageID string,
) (HomepageState, bool, error) {
	state, found := g[strings.TrimSpace(homepageID)]
	return state, found, nil
}

func newFacadeForTest(t *testing.T) (*Facade, *memoryStore) {
	t.Helper()
	store := newMemoryStore()
	facade, err := NewFacade(DataPorts{
		Aggregates: store,
		Receipts:   store,
		Queue:      store,
		Homepages: staticHomepageGate{
			"hp-open":    {Status: "published", ClaimStatus: "unclaimed"},
			"hp-claimed": {Status: "published", ClaimStatus: "claimed"},
			"hp-offline": {Status: "offline", ClaimStatus: "unclaimed"},
		},
	})
	if err != nil {
		t.Fatalf("new facade: %v", err)
	}
	base := time.Date(2026, 7, 20, 1, 0, 0, 0, time.UTC)
	step := 0
	facade.SetClock(func() time.Time {
		step++
		return base.Add(time.Duration(step) * time.Second)
	})
	id := 0
	facade.SetIDGenerator(func() string {
		id++
		return "claim-test-" + string(rune('0'+id))
	})
	return facade, store
}

func commandContext(key string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		OperationID:    "test",
		RequestID:      "req-test",
		TraceID:        "trace-test",
		IdempotencyKey: key,
	})
}

func validCreateCommand() CreateCommand {
	return CreateCommand{
		HomepageID:         "hp-open",
		ActorPersonaID:     "persona-requester",
		ClaimTier:          claimmodel.ClaimTierBasic,
		BusinessLicenseURL: "https://assets.test/license",
		ContactPhone:       "13800000000",
		Note:               "申请认领",
	}
}

func TestClaimCreateReceiptDuplicateAndCanonicalEvent(t *testing.T) {
	facade, store := newFacadeForTest(t)
	command := validCreateCommand()
	created, err := facade.Create(commandContext("claim-create"), command)
	if err != nil {
		t.Fatalf("create claim: %v", err)
	}
	if created.Version != 1 || created.Status != claimmodel.StatusPendingReview ||
		created.ClaimRequestID == "" {
		t.Fatalf("unexpected created claim: %+v", created)
	}
	replayed, err := facade.Create(commandContext("claim-create"), command)
	if err != nil || replayed.ClaimRequestID != created.ClaimRequestID {
		t.Fatalf("receipt replay mismatch: %+v err=%v", replayed, err)
	}
	changed := command
	changed.Note = "different digest"
	if _, err := facade.Create(commandContext("claim-create"), changed); !hasCode(
		err, generated.ErrIdempotencyConflict,
	) {
		t.Fatalf("digest reuse must conflict: %v", err)
	}
	if _, err := facade.Create(commandContext("claim-duplicate"), command); !hasCode(
		err, generated.ErrDuplicatePendingClaim,
	) {
		t.Fatalf("second pending claim must use duplicate_pending_claim: %v", err)
	}
	if len(store.outbox) != 1 {
		t.Fatalf("replay/duplicate must not append outbox: %d", len(store.outbox))
	}
	var payload claimRequestedPayload
	if err := json.Unmarshal(store.outbox[0].Payload, &payload); err != nil {
		t.Fatalf("decode claim event: %v", err)
	}
	raw := string(store.outbox[0].Payload)
	if payload.ClaimRequestID != created.ClaimRequestID ||
		!strings.Contains(raw, `"claimRequestId"`) ||
		strings.Contains(raw, `"_id"`) {
		t.Fatalf("claim event must use canonical claimRequestId: %s", raw)
	}
}

func TestClaimGovernanceQueueReturnsPendingReviewMaterial(t *testing.T) {
	facade, _ := newFacadeForTest(t)
	created, err := facade.Create(commandContext("claim-queue-create"), validCreateCommand())
	if err != nil {
		t.Fatalf("create claim: %v", err)
	}
	page, err := facade.ListQueue(context.Background(), QueueQuery{
		Status: claimmodel.StatusPendingReview,
		Limit:  20,
	})
	if err != nil {
		t.Fatalf("list claim governance queue: %v", err)
	}
	if len(page.Items) != 1 ||
		page.Items[0].ClaimRequestID != created.ClaimRequestID ||
		page.Items[0].BusinessLicenseURL == "" ||
		page.Items[0].ContactPhone == "" {
		t.Fatalf("governance queue must preserve review material: %+v", page)
	}
}

func TestClaimReviewGuardsCASNoopAndTerminalState(t *testing.T) {
	facade, store := newFacadeForTest(t)
	created, err := facade.Create(commandContext("claim-create-review"), validCreateCommand())
	if err != nil {
		t.Fatalf("create claim: %v", err)
	}
	base := ReviewCommand{
		HomepageID:     created.HomepageID,
		ClaimRequestID: created.ClaimRequestID,
		TargetStatus:   claimmodel.StatusApproved,
	}
	if _, err := facade.Review(commandContext("review-missing"), base); !hasCode(
		err, generated.ErrPermissionDenied,
	) {
		t.Fatalf("missing reviewer must be denied: %v", err)
	}
	self := base
	self.ActorAccountID = created.RequesterPersonaID
	if _, err := facade.Review(commandContext("review-self"), self); !hasCode(
		err, generated.ErrPermissionDenied,
	) {
		t.Fatalf("self review must be denied: %v", err)
	}
	store.forcedCASConflicts = 1
	review := base
	review.ActorAccountID = "account-operator"
	beforeCalls := store.commitCalls
	approved, err := facade.Review(commandContext("review-approved"), review)
	if err != nil {
		t.Fatalf("review after one CAS retry: %v", err)
	}
	if approved.Version != 2 || approved.Status != claimmodel.StatusApproved ||
		store.commitCalls-beforeCalls != 2 {
		t.Fatalf("review must retry one CAS conflict: %+v calls=%d", approved, store.commitCalls-beforeCalls)
	}
	noop, err := facade.Review(commandContext("review-approved-noop"), review)
	if err != nil || noop.Version != approved.Version {
		t.Fatalf("same terminal target must be no-op: %+v err=%v", noop, err)
	}
	opposite := review
	opposite.TargetStatus = claimmodel.StatusRejected
	if _, err := facade.Review(commandContext("review-opposite"), opposite); !hasCode(
		err, generated.ErrVersionConflict,
	) {
		t.Fatalf("terminal status change must conflict: %v", err)
	}
	if len(store.outbox) != 2 {
		t.Fatalf("no-op/opposite review must not append outbox: %d", len(store.outbox))
	}
	var payload claimReviewedPayload
	if err := json.Unmarshal(store.outbox[1].Payload, &payload); err != nil {
		t.Fatalf("decode reviewed event: %v", err)
	}
	raw := string(store.outbox[1].Payload)
	if payload.ClaimRequestID != created.ClaimRequestID ||
		strings.Contains(raw, `"_id"`) {
		t.Fatalf("reviewed event must use canonical claimRequestId: %s", raw)
	}
}

func TestClaimCASStopsAfterThreeAttemptsAndMaterialRules(t *testing.T) {
	facade, store := newFacadeForTest(t)
	invalid := validCreateCommand()
	invalid.BusinessLicenseURL = ""
	if _, err := facade.Create(commandContext("claim-material"), invalid); !hasCode(
		err, generated.ErrClaimMaterialMissing,
	) {
		t.Fatalf("basic claim without proof must fail: %v", err)
	}
	verified := validCreateCommand()
	verified.ClaimTier = claimmodel.ClaimTierVerified
	if _, err := facade.Create(commandContext("claim-verified-material"), verified); !hasCode(
		err, generated.ErrClaimMaterialMissing,
	) {
		t.Fatalf("verified claim requires identity pair: %v", err)
	}
	created, err := facade.Create(commandContext("claim-cas-create"), validCreateCommand())
	if err != nil {
		t.Fatalf("create claim: %v", err)
	}
	store.forcedCASConflicts = 3
	beforeCalls := store.commitCalls
	_, err = facade.Review(commandContext("claim-cas-review"), ReviewCommand{
		HomepageID:     created.HomepageID,
		ClaimRequestID: created.ClaimRequestID,
		ActorAccountID: "account-operator",
		TargetStatus:   claimmodel.StatusRejected,
	})
	if !hasCode(err, generated.ErrVersionConflict) {
		t.Fatalf("three CAS conflicts must surface version conflict: %v", err)
	}
	if attempts := store.commitCalls - beforeCalls; attempts != 3 {
		t.Fatalf("CAS retries must stop at three attempts, got %d", attempts)
	}
}

func TestClaimHomepageGate(t *testing.T) {
	facade, _ := newFacadeForTest(t)
	for name, testCase := range map[string]struct {
		homepageID string
		code       error
	}{
		"missing": {"hp-missing", generated.ErrHomepageNotFound},
		"offline": {"hp-offline", generated.ErrHomepageOffline},
		"claimed": {"hp-claimed", generated.ErrAlreadyClaimed},
	} {
		t.Run(name, func(t *testing.T) {
			command := validCreateCommand()
			command.HomepageID = testCase.homepageID
			if _, err := facade.Create(commandContext("gate-"+name), command); !hasCode(
				err, testCase.code,
			) {
				t.Fatalf("unexpected gate error: %v", err)
			}
		})
	}
}

func hasCode(err error, sentinel error) bool {
	if err == nil || sentinel == nil {
		return false
	}
	var appError *rterr.AppError
	return errors.As(err, &appError) && appError.Code.String() == sentinel.Error()
}
