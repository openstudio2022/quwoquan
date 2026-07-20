package homepage_status_report

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
	reportmodel "quwoquan_service/services/entity-service/internal/domain/homepage_status_report/model"
	reportports "quwoquan_service/services/entity-service/internal/domain/homepage_status_report/ports"
	"quwoquan_service/services/entity-service/internal/generated"
)

type memoryReceipt struct {
	commandName   string
	commandDigest string
	snapshot      reportmodel.Snapshot
}

type memoryStore struct {
	mu                 sync.Mutex
	reports            map[string]reportmodel.Snapshot
	receipts           map[string]memoryReceipt
	outbox             []reportports.OutboxEvent
	forcedCASConflicts int
	commitCalls        int
}

func newMemoryStore() *memoryStore {
	return &memoryStore{
		reports:  make(map[string]reportmodel.Snapshot),
		receipts: make(map[string]memoryReceipt),
	}
}

func (s *memoryStore) Load(
	_ context.Context,
	reportID string,
) (*reportmodel.HomepageStatusReport, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	snapshot, found := s.reports[strings.TrimSpace(reportID)]
	if !found {
		return nil, false, nil
	}
	aggregate, err := reportmodel.Restore(snapshot)
	return aggregate, err == nil, err
}

func (s *memoryStore) FindPending(
	_ context.Context,
	homepageID string,
	reporterPersonaID string,
	reason reportmodel.Reason,
) (*reportmodel.HomepageStatusReport, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, snapshot := range s.reports {
		if snapshot.HomepageID == strings.TrimSpace(homepageID) &&
			snapshot.ReporterPersonaID == strings.TrimSpace(reporterPersonaID) &&
			snapshot.Reason == reason &&
			snapshot.Status == reportmodel.StatusPendingReview {
			aggregate, err := reportmodel.Restore(snapshot)
			return aggregate, err == nil, err
		}
	}
	return nil, false, nil
}

func (s *memoryStore) ListQueue(
	_ context.Context,
	query reportports.QueueQuery,
) (reportports.QueuePage, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	items := make([]reportmodel.Snapshot, 0, len(s.reports))
	for _, snapshot := range s.reports {
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
	return reportports.QueuePage{Items: append([]reportmodel.Snapshot(nil), items[:limit]...)}, nil
}

func (s *memoryStore) FindReceipt(
	_ context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (reportports.CommitResult, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receipt, found := s.receipts[idempotencyKey]
	if !found {
		return reportports.CommitResult{}, false, nil
	}
	if receipt.commandName != commandName || receipt.commandDigest != commandDigest {
		return reportports.CommitResult{}, false,
			generated.AppErrorFromIdempotencyConflict("status report receipt digest mismatch")
	}
	aggregate, err := reportmodel.Restore(receipt.snapshot)
	return reportports.CommitResult{Aggregate: aggregate, Replayed: true}, err == nil, err
}

func (s *memoryStore) RecordNoopReceipt(
	_ context.Context,
	noop reportports.NoopReceipt,
) (reportports.CommitResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if receipt, found := s.receipts[noop.IdempotencyKey]; found {
		if receipt.commandName != noop.CommandName || receipt.commandDigest != noop.CommandDigest {
			return reportports.CommitResult{},
				generated.AppErrorFromIdempotencyConflict("status report receipt digest mismatch")
		}
		aggregate, err := reportmodel.Restore(receipt.snapshot)
		return reportports.CommitResult{Aggregate: aggregate, Replayed: true}, err
	}
	snapshot := noop.Aggregate.Snapshot()
	s.receipts[noop.IdempotencyKey] = memoryReceipt{
		commandName:   noop.CommandName,
		commandDigest: noop.CommandDigest,
		snapshot:      snapshot,
	}
	aggregate, err := reportmodel.Restore(snapshot)
	return reportports.CommitResult{Aggregate: aggregate}, err
}

func (s *memoryStore) Commit(
	_ context.Context,
	commit reportports.Commit,
) (reportports.CommitResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.commitCalls++
	if receipt, found := s.receipts[commit.IdempotencyKey]; found {
		if receipt.commandName != commit.CommandName || receipt.commandDigest != commit.CommandDigest {
			return reportports.CommitResult{},
				generated.AppErrorFromIdempotencyConflict("status report receipt digest mismatch")
		}
		aggregate, err := reportmodel.Restore(receipt.snapshot)
		return reportports.CommitResult{Aggregate: aggregate, Replayed: true}, err
	}
	if s.forcedCASConflicts > 0 {
		s.forcedCASConflicts--
		return reportports.CommitResult{},
			generated.AppErrorFromVersionConflict("forced status report CAS conflict")
	}
	snapshot := commit.Aggregate.Snapshot()
	current, exists := s.reports[snapshot.ID]
	if commit.ExpectedVersion == 0 {
		for _, candidate := range s.reports {
			if candidate.HomepageID == snapshot.HomepageID &&
				candidate.ReporterPersonaID == snapshot.ReporterPersonaID &&
				candidate.Reason == snapshot.Reason &&
				candidate.Status == reportmodel.StatusPendingReview {
				return reportports.CommitResult{},
					generated.AppErrorFromInvalidArgument("duplicate pending status report")
			}
		}
		if exists {
			return reportports.CommitResult{},
				generated.AppErrorFromVersionConflict("status report ID already exists")
		}
	} else if !exists || current.Version != commit.ExpectedVersion {
		return reportports.CommitResult{},
			generated.AppErrorFromVersionConflict("status report version changed")
	}
	s.reports[snapshot.ID] = snapshot
	s.receipts[commit.IdempotencyKey] = memoryReceipt{
		commandName:   commit.CommandName,
		commandDigest: commit.CommandDigest,
		snapshot:      snapshot,
	}
	s.outbox = append(s.outbox, commit.Events...)
	aggregate, err := reportmodel.Restore(snapshot)
	return reportports.CommitResult{Aggregate: aggregate}, err
}

type staticHomepageGate map[string]string

func (g staticHomepageGate) FindHomepageStatus(
	_ context.Context,
	homepageID string,
) (string, bool, error) {
	status, found := g[strings.TrimSpace(homepageID)]
	return status, found, nil
}

func newFacadeForTest(t *testing.T) (*Facade, *memoryStore) {
	t.Helper()
	store := newMemoryStore()
	facade, err := NewFacade(DataPorts{
		Aggregates: store,
		Receipts:   store,
		Queue:      store,
		Homepages: staticHomepageGate{
			"hp-open":    "published",
			"hp-offline": "offline",
		},
	})
	if err != nil {
		t.Fatalf("new facade: %v", err)
	}
	base := time.Date(2026, 7, 20, 2, 0, 0, 0, time.UTC)
	step := 0
	facade.SetClock(func() time.Time {
		step++
		return base.Add(time.Duration(step) * time.Second)
	})
	id := 0
	facade.SetIDGenerator(func() string {
		id++
		return "report-test-" + string(rune('0'+id))
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
		HomepageID:     "hp-open",
		ActorPersonaID: "persona-reporter",
		Reason:         reportmodel.ReasonOffline,
		Description:    "门店已经关闭",
		EvidenceURLs:   []string{"https://assets.test/offline-proof"},
	}
}

func TestStatusReportCreateReceiptPendingUniqueAndCanonicalEvent(t *testing.T) {
	facade, store := newFacadeForTest(t)
	command := validCreateCommand()
	created, err := facade.Create(commandContext("report-create"), command)
	if err != nil {
		t.Fatalf("create status report: %v", err)
	}
	if created.Version != 1 || created.Status != reportmodel.StatusPendingReview ||
		created.ReportID == "" {
		t.Fatalf("unexpected created status report: %+v", created)
	}
	replayed, err := facade.Create(commandContext("report-create"), command)
	if err != nil || replayed.ReportID != created.ReportID {
		t.Fatalf("receipt replay mismatch: %+v err=%v", replayed, err)
	}
	changed := command
	changed.Description = "different digest"
	if _, err := facade.Create(commandContext("report-create"), changed); !hasCode(
		err, generated.ErrIdempotencyConflict,
	) {
		t.Fatalf("digest reuse must conflict: %v", err)
	}
	if _, err := facade.Create(commandContext("report-duplicate"), command); !hasCode(
		err, generated.ErrInvalidArgument,
	) {
		t.Fatalf("second pending report must be rejected: %v", err)
	}
	if len(store.outbox) != 1 {
		t.Fatalf("replay/duplicate must not append outbox: %d", len(store.outbox))
	}
	var payload statusReportedPayload
	if err := json.Unmarshal(store.outbox[0].Payload, &payload); err != nil {
		t.Fatalf("decode status report event: %v", err)
	}
	raw := string(store.outbox[0].Payload)
	if payload.ReportID != created.ReportID ||
		!strings.Contains(raw, `"reportId"`) ||
		strings.Contains(raw, `"_id"`) {
		t.Fatalf("status event must use canonical reportId: %s", raw)
	}
}

func TestStatusReportGovernanceQueueReturnsPendingEvidence(t *testing.T) {
	facade, _ := newFacadeForTest(t)
	created, err := facade.Create(commandContext("report-queue-create"), validCreateCommand())
	if err != nil {
		t.Fatalf("create status report: %v", err)
	}
	page, err := facade.ListQueue(context.Background(), QueueQuery{
		Status: reportmodel.StatusPendingReview,
		Limit:  20,
	})
	if err != nil {
		t.Fatalf("list status report governance queue: %v", err)
	}
	if len(page.Items) != 1 ||
		page.Items[0].ReportID != created.ReportID ||
		len(page.Items[0].EvidenceURLs) != 1 ||
		page.Items[0].Description == "" {
		t.Fatalf("governance queue must preserve report evidence: %+v", page)
	}
}

func TestStatusReportReviewGuardsCASNoopAndTerminalState(t *testing.T) {
	facade, store := newFacadeForTest(t)
	created, err := facade.Create(commandContext("report-create-review"), validCreateCommand())
	if err != nil {
		t.Fatalf("create status report: %v", err)
	}
	base := ReviewCommand{
		HomepageID:   created.HomepageID,
		ReportID:     created.ReportID,
		TargetStatus: reportmodel.StatusConfirmedOffline,
	}
	if _, err := facade.Review(commandContext("report-review-missing"), base); !hasCode(
		err, generated.ErrPermissionDenied,
	) {
		t.Fatalf("missing reviewer must be denied: %v", err)
	}
	self := base
	self.ActorAccountID = created.ReporterPersonaID
	if _, err := facade.Review(commandContext("report-review-self"), self); !hasCode(
		err, generated.ErrPermissionDenied,
	) {
		t.Fatalf("self review must be denied: %v", err)
	}
	store.forcedCASConflicts = 1
	review := base
	review.ActorAccountID = "account-operator"
	beforeCalls := store.commitCalls
	confirmed, err := facade.Review(commandContext("report-review-confirm"), review)
	if err != nil {
		t.Fatalf("review after one CAS retry: %v", err)
	}
	if confirmed.Version != 2 ||
		confirmed.Status != reportmodel.StatusConfirmedOffline ||
		store.commitCalls-beforeCalls != 2 {
		t.Fatalf("review must retry one CAS conflict: %+v calls=%d", confirmed, store.commitCalls-beforeCalls)
	}
	noop, err := facade.Review(commandContext("report-review-noop"), review)
	if err != nil || noop.Version != confirmed.Version {
		t.Fatalf("same terminal target must be no-op: %+v err=%v", noop, err)
	}
	opposite := review
	opposite.TargetStatus = reportmodel.StatusDismissed
	if _, err := facade.Review(commandContext("report-review-opposite"), opposite); !hasCode(
		err, generated.ErrVersionConflict,
	) {
		t.Fatalf("terminal status change must conflict: %v", err)
	}
	if len(store.outbox) != 2 {
		t.Fatalf("no-op/opposite review must not append outbox: %d", len(store.outbox))
	}
	var payload statusReportReviewedPayload
	if err := json.Unmarshal(store.outbox[1].Payload, &payload); err != nil {
		t.Fatalf("decode reviewed status event: %v", err)
	}
	raw := string(store.outbox[1].Payload)
	if payload.ReportID != created.ReportID || strings.Contains(raw, `"_id"`) {
		t.Fatalf("reviewed status event must use canonical reportId: %s", raw)
	}
}

func TestStatusReportCASStopsAfterThreeAttemptsAndReasonValidation(t *testing.T) {
	facade, store := newFacadeForTest(t)
	invalid := validCreateCommand()
	invalid.Reason = "unsupported"
	if _, err := facade.Create(commandContext("report-invalid-reason"), invalid); !hasCode(
		err, generated.ErrInvalidArgument,
	) {
		t.Fatalf("unsupported reason must fail: %v", err)
	}
	created, err := facade.Create(commandContext("report-cas-create"), validCreateCommand())
	if err != nil {
		t.Fatalf("create status report: %v", err)
	}
	store.forcedCASConflicts = 3
	beforeCalls := store.commitCalls
	_, err = facade.Review(commandContext("report-cas-review"), ReviewCommand{
		HomepageID:     created.HomepageID,
		ReportID:       created.ReportID,
		ActorAccountID: "account-operator",
		TargetStatus:   reportmodel.StatusDismissed,
	})
	if !hasCode(err, generated.ErrVersionConflict) {
		t.Fatalf("three CAS conflicts must surface version conflict: %v", err)
	}
	if attempts := store.commitCalls - beforeCalls; attempts != 3 {
		t.Fatalf("CAS retries must stop at three attempts, got %d", attempts)
	}
}

func TestStatusReportHomepageMustExist(t *testing.T) {
	facade, _ := newFacadeForTest(t)
	command := validCreateCommand()
	command.HomepageID = "hp-missing"
	if _, err := facade.Create(commandContext("report-homepage-missing"), command); !hasCode(
		err, generated.ErrHomepageNotFound,
	) {
		t.Fatalf("missing homepage must be rejected: %v", err)
	}
}

func hasCode(err error, sentinel error) bool {
	if err == nil || sentinel == nil {
		return false
	}
	var appError *rterr.AppError
	return errors.As(err, &appError) && appError.Code.String() == sentinel.Error()
}
