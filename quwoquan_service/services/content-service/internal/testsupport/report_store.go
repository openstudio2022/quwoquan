package testsupport

import (
	"context"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	reportapp "quwoquan_service/services/content-service/internal/application/report"
	reportmodel "quwoquan_service/services/content-service/internal/domain/report/model"
	reportports "quwoquan_service/services/content-service/internal/domain/report/ports"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

type reportReceipt struct {
	commandName   string
	commandDigest string
	snapshot      reportmodel.Snapshot
	expiresAt     time.Time
}

type reportOutboxRecord struct {
	event    reportports.OutboxEvent
	sequence int64
}

type ReportStore struct {
	mu              sync.RWMutex
	reports         map[string]reportmodel.Snapshot
	receipts        map[string]reportReceipt
	outbox          []reportOutboxRecord
	nextOutboxSeq   int64
	checkpoints     map[string]reportports.OutboxCheckpoint
	activeConsumers map[string]bool
}

func NewReportStore() *ReportStore {
	return &ReportStore{
		reports:         map[string]reportmodel.Snapshot{},
		receipts:        map[string]reportReceipt{},
		checkpoints:     map[string]reportports.OutboxCheckpoint{},
		activeConsumers: map[string]bool{},
	}
}

func (s *ReportStore) Load(
	_ context.Context,
	reportID string,
) (*reportmodel.Report, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	snapshot, found := s.reports[reportID]
	if !found {
		return nil, false, nil
	}
	aggregate, err := reportmodel.Restore(snapshot)
	if err != nil {
		return nil, false, err
	}
	return aggregate, true, nil
}

func (s *ReportStore) FindReceipt(
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
	if !receipt.expiresAt.After(time.Now().UTC()) {
		delete(s.receipts, idempotencyKey)
		return reportports.CommitResult{}, false, nil
	}
	if receipt.commandName != commandName ||
		receipt.commandDigest != commandDigest {
		return reportports.CommitResult{},
			false,
			contentgenerated.AppErrorFromIdempotencyConflict(
				"test report receipt digest mismatch",
			)
	}
	replayed, err := reportmodel.Restore(receipt.snapshot)
	if err != nil {
		return reportports.CommitResult{}, false, err
	}
	return reportports.CommitResult{
		Aggregate: replayed,
		Replayed:  true,
	}, true, nil
}

func (s *ReportStore) Commit(
	_ context.Context,
	commit reportports.Commit,
) (reportports.CommitResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if receipt, found := s.receipts[commit.IdempotencyKey]; found {
		if !receipt.expiresAt.After(time.Now().UTC()) {
			delete(s.receipts, commit.IdempotencyKey)
		} else {
			if receipt.commandName != commit.CommandName ||
				receipt.commandDigest != commit.CommandDigest {
				return reportports.CommitResult{},
					contentgenerated.AppErrorFromIdempotencyConflict(
						"test report receipt digest mismatch",
					)
			}
			replayed, err := reportmodel.Restore(receipt.snapshot)
			if err != nil {
				return reportports.CommitResult{}, err
			}
			return reportports.CommitResult{
				Aggregate: replayed,
				Replayed:  true,
			}, nil
		}
	}
	if commit.Aggregate == nil {
		return reportports.CommitResult{},
			contentgenerated.AppErrorFromVersionConflict(
				"report aggregate is required",
			)
	}
	snapshot := commit.Aggregate.Snapshot()
	current, exists := s.reports[snapshot.ID]
	if commit.ExpectedVersion == 0 {
		if exists {
			return reportports.CommitResult{},
				contentgenerated.AppErrorFromVersionConflict(
					"report already exists",
				)
		}
	} else if !exists || current.Version != commit.ExpectedVersion {
		return reportports.CommitResult{},
			contentgenerated.AppErrorFromVersionConflict(
				"report version changed",
			)
	}
	if snapshot.Version != commit.ExpectedVersion+1 {
		return reportports.CommitResult{},
			contentgenerated.AppErrorFromVersionConflict(
				"report aggregate version is not monotonic",
			)
	}
	for _, event := range commit.Events {
		if event.AggregateID != snapshot.ID ||
			event.AggregateVersion != snapshot.Version {
			return reportports.CommitResult{},
				contentgenerated.AppErrorFromVersionConflict(
					"report fact version does not match aggregate",
				)
		}
	}
	s.reports[snapshot.ID] = snapshot
	expiresAt := commit.ReceiptExpiresAt
	if expiresAt.IsZero() {
		expiresAt = time.Now().UTC().Add(24 * time.Hour)
	}
	s.receipts[commit.IdempotencyKey] = reportReceipt{
		commandName:   commit.CommandName,
		commandDigest: commit.CommandDigest,
		snapshot:      snapshot,
		expiresAt:     expiresAt,
	}
	for _, event := range cloneOutboxEvents(commit.Events) {
		s.nextOutboxSeq++
		s.outbox = append(s.outbox, reportOutboxRecord{
			event:    event,
			sequence: s.nextOutboxSeq,
		})
	}
	aggregate, err := reportmodel.Restore(snapshot)
	if err != nil {
		return reportports.CommitResult{}, err
	}
	return reportports.CommitResult{Aggregate: aggregate}, nil
}

func (s *ReportStore) FindByID(
	_ context.Context,
	reportID string,
) (reportapp.ReportDetailSlice, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	snapshot, found := s.reports[reportID]
	if !found {
		return reportapp.ReportDetailSlice{}, false, nil
	}
	return reportDetailFromSnapshot(snapshot), true, nil
}

func (s *ReportStore) List(
	_ context.Context,
	limit int,
) (reportapp.ReportQueueSlice, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	snapshots := make([]reportmodel.Snapshot, 0, len(s.reports))
	for _, snapshot := range s.reports {
		snapshots = append(snapshots, snapshot)
	}
	sort.Slice(snapshots, func(i, j int) bool {
		return snapshots[i].CreatedAt.After(snapshots[j].CreatedAt)
	})
	if limit > 0 && len(snapshots) > limit {
		snapshots = snapshots[:limit]
	}
	items := make([]reportapp.ReportQueueItemSlice, 0, len(snapshots))
	for _, snapshot := range snapshots {
		items = append(items, reportapp.ReportQueueItemSlice{
			ID:         snapshot.ID,
			Version:    snapshot.Version,
			TargetType: snapshot.TargetType,
			TargetID:   snapshot.TargetID,
			Reason:     snapshot.Reason,
			Status:     snapshot.Status,
			CreatedAt:  snapshot.CreatedAt,
			UpdatedAt:  snapshot.UpdatedAt,
		})
	}
	return reportapp.ReportQueueSlice{Items: items, Total: len(items)}, nil
}

func (s *ReportStore) OutboxEvents() []reportports.OutboxEvent {
	s.mu.RLock()
	defer s.mu.RUnlock()
	events := make([]reportports.OutboxEvent, 0, len(s.outbox))
	for _, record := range s.outbox {
		events = append(events, record.event)
	}
	return cloneOutboxEvents(events)
}

// ReadAfter 镜像生产 Reader 的稳定重放顺序 outbox_sequence ASC。它只返回
// 不透明 checkpoint 之后的事实，绝不从时间戳或切片位置推导 checkpoint。
func (s *ReportStore) ReadAfter(
	_ context.Context,
	checkpoint reportports.OutboxCheckpoint,
	limit int,
) ([]reportports.OutboxEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	if limit > 1000 {
		limit = 1000
	}

	s.mu.RLock()
	records := append([]reportOutboxRecord(nil), s.outbox...)
	s.mu.RUnlock()
	sort.Slice(records, func(left, right int) bool {
		return records[left].sequence < records[right].sequence
	})

	start := 0
	if strings.TrimSpace(string(checkpoint)) != "" {
		found := false
		for index, record := range records {
			if reportOutboxCheckpoint(record.sequence) == checkpoint {
				start = index + 1
				found = true
				break
			}
		}
		if !found {
			return nil, fmt.Errorf("unknown local Report outbox checkpoint %q", checkpoint)
		}
	}

	end := start + limit
	if end > len(records) {
		end = len(records)
	}
	events := make([]reportports.OutboxEvent, 0, end-start)
	for _, record := range records[start:end] {
		event := record.event
		event.Payload = append([]byte(nil), event.Payload...)
		event.Checkpoint = reportOutboxCheckpoint(record.sequence)
		events = append(events, event)
	}
	return events, nil
}

// AcquireCheckpoint 是生产 consumer 行锁的 local_contract 等价实现：同一
// consumer 同时只能推进一个待提交 checkpoint，不同 consumer 从各自水位开始。
func (s *ReportStore) AcquireCheckpoint(
	_ context.Context,
	consumer string,
) (reportports.ProjectionCheckpointLease, bool, error) {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return nil, false, fmt.Errorf("Report projection consumer is required")
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	if s.activeConsumers[consumer] {
		return nil, false, nil
	}
	s.activeConsumers[consumer] = true
	return &reportCheckpointLease{
		store:      s,
		consumer:   consumer,
		checkpoint: s.checkpoints[consumer],
	}, true, nil
}

type reportCheckpointLease struct {
	mu sync.Mutex

	store      *ReportStore
	consumer   string
	checkpoint reportports.OutboxCheckpoint
	closed     bool
}

func (l *reportCheckpointLease) Checkpoint() reportports.OutboxCheckpoint {
	if l == nil {
		return ""
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.checkpoint
}

func (l *reportCheckpointLease) SaveCheckpoint(
	_ context.Context,
	checkpoint reportports.OutboxCheckpoint,
) error {
	if l == nil {
		return fmt.Errorf("Report checkpoint lease is nil")
	}
	if strings.TrimSpace(string(checkpoint)) == "" {
		return fmt.Errorf("Report projection checkpoint is required")
	}

	l.mu.Lock()
	defer l.mu.Unlock()
	if l.closed {
		return fmt.Errorf("Report checkpoint lease is closed")
	}
	if l.checkpoint != "" {
		order, err := compareReportOutboxCheckpoints(l.checkpoint, checkpoint)
		if err != nil {
			return err
		}
		if order > 0 {
			return fmt.Errorf("Report projection checkpoint cannot move backward")
		}
		if order == 0 {
			return nil
		}
	}
	l.checkpoint = checkpoint
	return nil
}

func (l *reportCheckpointLease) Commit(_ context.Context) error {
	if l == nil {
		return fmt.Errorf("Report checkpoint lease is nil")
	}
	return l.release(true)
}

func (l *reportCheckpointLease) Rollback() error {
	if l == nil {
		return nil
	}
	return l.release(false)
}

func (l *reportCheckpointLease) release(commit bool) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.closed {
		return nil
	}
	l.closed = true

	l.store.mu.Lock()
	defer l.store.mu.Unlock()
	if !l.store.activeConsumers[l.consumer] {
		return fmt.Errorf("Report checkpoint lease is not active")
	}
	if commit {
		l.store.checkpoints[l.consumer] = l.checkpoint
	}
	delete(l.store.activeConsumers, l.consumer)
	return nil
}

func reportDetailFromSnapshot(
	snapshot reportmodel.Snapshot,
) reportapp.ReportDetailSlice {
	return reportapp.ReportDetailSlice{
		ID:          snapshot.ID,
		Version:     snapshot.Version,
		ReporterID:  snapshot.ReporterID,
		TargetType:  snapshot.TargetType,
		TargetID:    snapshot.TargetID,
		Reason:      snapshot.Reason,
		Description: snapshot.Description,
		Status:      snapshot.Status,
		ReviewerID:  snapshot.ReviewerID,
		Resolution:  snapshot.Resolution,
		CreatedAt:   snapshot.CreatedAt,
		UpdatedAt:   snapshot.UpdatedAt,
		ResolvedAt:  snapshot.ResolvedAt,
	}
}

func cloneOutboxEvents(
	events []reportports.OutboxEvent,
) []reportports.OutboxEvent {
	cloned := make([]reportports.OutboxEvent, len(events))
	for index, event := range events {
		cloned[index] = event
		cloned[index].Payload = append([]byte(nil), event.Payload...)
	}
	return cloned
}

func reportOutboxCheckpoint(
	sequence int64,
) reportports.OutboxCheckpoint {
	return reportports.OutboxCheckpoint(strconv.FormatInt(sequence, 10))
}

func compareReportOutboxCheckpoints(
	left reportports.OutboxCheckpoint,
	right reportports.OutboxCheckpoint,
) (int, error) {
	leftSequence, err := parseReportOutboxCheckpoint(left)
	if err != nil {
		return 0, err
	}
	rightSequence, err := parseReportOutboxCheckpoint(right)
	if err != nil {
		return 0, err
	}
	switch {
	case leftSequence < rightSequence:
		return -1, nil
	case leftSequence > rightSequence:
		return 1, nil
	default:
		return 0, nil
	}
}

func parseReportOutboxCheckpoint(
	checkpoint reportports.OutboxCheckpoint,
) (int64, error) {
	sequence, err := strconv.ParseInt(
		strings.TrimSpace(string(checkpoint)),
		10,
		64,
	)
	if err != nil || sequence <= 0 {
		return 0, fmt.Errorf("invalid Report outbox checkpoint")
	}
	return sequence, nil
}

var (
	_ reportports.OutboxReader              = (*ReportStore)(nil)
	_ reportports.ProjectionCheckpointStore = (*ReportStore)(nil)
)
