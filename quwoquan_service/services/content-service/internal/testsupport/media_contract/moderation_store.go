package mediacontract

import (
	"context"
	"strings"
	"sync"
	"time"

	moderationmodel "quwoquan_service/services/content-service/internal/domain/moderation/model"
	moderationports "quwoquan_service/services/content-service/internal/domain/moderation/ports"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

// ModerationStore is test-only contract infrastructure for PostModerationCase.
// Production composition must use MongoPostModerationCaseStore.
type ModerationStore struct {
	mu       sync.RWMutex
	cases    map[string]moderationmodel.Snapshot
	receipts map[string]moderationReceipt
	outbox   []moderationports.OutboxEvent
	audit    []moderationports.AuditEntry
}

type moderationReceipt struct {
	name     string
	digest   string
	snapshot moderationmodel.Snapshot
	expiry   time.Time
}

func NewModerationStore() *ModerationStore {
	return &ModerationStore{
		cases:    map[string]moderationmodel.Snapshot{},
		receipts: map[string]moderationReceipt{},
	}
}

func (s *ModerationStore) Load(
	_ context.Context,
	caseID string,
) (*moderationmodel.PostModerationCase, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	snapshot, found := s.cases[caseID]
	if !found {
		return nil, false, nil
	}
	aggregate, err := moderationmodel.Restore(snapshot)
	return aggregate, err == nil, err
}

func (s *ModerationStore) LoadByPostRevision(
	_ context.Context,
	postID string,
	postVersion int64,
	contentDigest string,
) (*moderationmodel.PostModerationCase, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	for _, snapshot := range s.cases {
		if snapshot.PostID != postID ||
			snapshot.PostVersion != postVersion ||
			snapshot.ContentDigest != normalizeDigest(contentDigest) {
			continue
		}
		aggregate, err := moderationmodel.Restore(snapshot)
		return aggregate, err == nil, err
	}
	return nil, false, nil
}

func (s *ModerationStore) FindReceipt(
	_ context.Context,
	key string,
	name string,
	digest string,
) (moderationports.CommitResult, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receipt, found, err := s.receipt(key, name, digest)
	if err != nil || !found {
		return moderationports.CommitResult{}, found, err
	}
	aggregate, err := moderationmodel.Restore(receipt.snapshot)
	if err != nil {
		return moderationports.CommitResult{}, false, err
	}
	return moderationports.CommitResult{Aggregate: aggregate, Replayed: true}, true, nil
}

func (s *ModerationStore) Commit(
	_ context.Context,
	commit moderationports.Commit,
) (moderationports.CommitResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receipt, found, err := s.receipt(
		commit.IdempotencyKey,
		commit.CommandName,
		commit.CommandDigest,
	)
	if err != nil {
		return moderationports.CommitResult{}, err
	}
	if found {
		aggregate, restoreErr := moderationmodel.Restore(receipt.snapshot)
		return moderationports.CommitResult{Aggregate: aggregate, Replayed: true}, restoreErr
	}
	if err := s.validateCommit(commit); err != nil {
		return moderationports.CommitResult{}, err
	}
	snapshot := commit.Aggregate.Snapshot()
	s.cases[snapshot.ID] = snapshot
	s.receipts[commit.IdempotencyKey] = moderationReceipt{
		name:     commit.CommandName,
		digest:   commit.CommandDigest,
		snapshot: snapshot,
		expiry:   receiptExpiry(commit.ReceiptExpiresAt),
	}
	s.outbox = append(s.outbox, cloneModerationOutbox(commit.Events)...)
	s.audit = append(s.audit, commit.Audit)
	aggregate, err := moderationmodel.Restore(snapshot)
	return moderationports.CommitResult{Aggregate: aggregate}, err
}

func (s *ModerationStore) GetPublicationEligibility(
	_ context.Context,
	query moderationports.PublicationEligibilityQuery,
) (moderationports.PublicationEligibility, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	now := time.Now().UTC()
	for _, snapshot := range s.cases {
		if snapshot.PostID != query.PostID ||
			snapshot.PostVersion != query.PostVersion ||
			snapshot.ContentDigest != normalizeDigest(query.ContentDigest) {
			continue
		}
		eligible := snapshot.Status == moderationmodel.StatusApproved
		failureReason := ""
		if !eligible {
			failureReason = "moderation_approval_required"
		}
		return moderationports.PublicationEligibility{
			Eligible:      eligible,
			CaseID:        snapshot.ID,
			CaseVersion:   snapshot.Version,
			Moderation:    snapshot.Status,
			CheckedAt:     now,
			DecisionAt:    cloneTime(snapshot.DecidedAt),
			FailureReason: failureReason,
		}, nil
	}
	return moderationports.PublicationEligibility{
		CheckedAt:     now,
		FailureReason: "moderation_approval_required",
	}, nil
}

func (s *ModerationStore) OutboxEvents() []moderationports.OutboxEvent {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return cloneModerationOutbox(s.outbox)
}

func (s *ModerationStore) AuditEntries() []moderationports.AuditEntry {
	s.mu.RLock()
	defer s.mu.RUnlock()
	cloned := make([]moderationports.AuditEntry, len(s.audit))
	copy(cloned, s.audit)
	return cloned
}

func (s *ModerationStore) receipt(
	key string,
	name string,
	digest string,
) (moderationReceipt, bool, error) {
	receipt, found := s.receipts[key]
	if !found {
		return moderationReceipt{}, false, nil
	}
	if !receipt.expiry.After(time.Now().UTC()) {
		delete(s.receipts, key)
		return moderationReceipt{}, false, nil
	}
	if receipt.name != name || receipt.digest != digest {
		return moderationReceipt{}, false,
			contentgenerated.AppErrorFromIdempotencyConflict(
				"test moderation receipt command mismatch",
			)
	}
	return receipt, true, nil
}

func (s *ModerationStore) validateCommit(commit moderationports.Commit) error {
	if commit.Aggregate == nil ||
		commit.Aggregate.Version() != commit.ExpectedVersion+1 ||
		commit.IdempotencyKey == "" ||
		commit.Audit.CaseID != commit.Aggregate.ID() ||
		commit.Audit.CaseVersion != commit.Aggregate.Version() ||
		commit.Audit.Action == "" ||
		len(commit.Events) != 1 {
		return contentgenerated.AppErrorFromVersionConflict(
			"invalid test moderation commit",
		)
	}
	current, exists := s.cases[commit.Aggregate.ID()]
	if commit.ExpectedVersion == 0 {
		if exists {
			return contentgenerated.AppErrorFromVersionConflict(
				"test moderation case already exists",
			)
		}
	} else if !exists || current.Version != commit.ExpectedVersion {
		return contentgenerated.AppErrorFromVersionConflict(
			"test moderation case version changed",
		)
	}
	event := commit.Events[0]
	if event.AggregateID != commit.Aggregate.ID() ||
		event.AggregateVersion != commit.Aggregate.Version() {
		return contentgenerated.AppErrorFromVersionConflict(
			"test moderation outbox version mismatch",
		)
	}
	return nil
}

func cloneModerationOutbox(
	events []moderationports.OutboxEvent,
) []moderationports.OutboxEvent {
	cloned := make([]moderationports.OutboxEvent, len(events))
	for index, event := range events {
		cloned[index] = event
		cloned[index].Payload = append([]byte(nil), event.Payload...)
	}
	return cloned
}

func normalizeDigest(value string) string {
	return strings.ToLower(strings.TrimSpace(value))
}
