package persistence

import (
	"context"
	"encoding/json"
	"sync"
	"time"

	"quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/domain/model"
	"quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/domain/ports"
)

type MemoryStore struct {
	mu          sync.Mutex
	units       map[string]model.DecisionUnit
	events      map[string][]model.Event
	github      map[string]model.GitHubApproval
	idempotency map[string]ports.IdempotencyRecord
	outbox      []ports.OutboxRecord
}

func NewMemoryStore() *MemoryStore {
	return &MemoryStore{units: map[string]model.DecisionUnit{}, events: map[string][]model.Event{}, github: map[string]model.GitHubApproval{}, idempotency: map[string]ports.IdempotencyRecord{}}
}
func (s *MemoryStore) EnsureSchema(context.Context) error { return nil }
func cloneUnit(u model.DecisionUnit) model.DecisionUnit {
	raw, _ := json.Marshal(u)
	var out model.DecisionUnit
	_ = json.Unmarshal(raw, &out)
	return out
}
func (s *MemoryStore) Load(_ context.Context, id string) (model.DecisionUnit, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	u, ok := s.units[id]
	if !ok {
		return model.DecisionUnit{}, model.ErrNotFound
	}
	return cloneUnit(u), nil
}
func (s *MemoryStore) Events(_ context.Context, id string) ([]model.Event, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.units[id]; !ok {
		return nil, model.ErrNotFound
	}
	out := append([]model.Event(nil), s.events[id]...)
	return out, nil
}
func (s *MemoryStore) List(_ context.Context) ([]model.DecisionUnit, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]model.DecisionUnit, 0, len(s.units))
	for _, unit := range s.units {
		out = append(out, cloneUnit(unit))
	}
	return out, nil
}
func (s *MemoryStore) Receipt(_ context.Context, decisionID string) (model.AuthorizationReceipt, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, unit := range s.units {
		if unit.Receipt != nil && unit.Receipt.DecisionID == decisionID {
			return *unit.Receipt, nil
		}
	}
	return model.AuthorizationReceipt{}, model.ErrNotFound
}
func (s *MemoryStore) Idempotency(_ context.Context, operation, key string) (ports.IdempotencyRecord, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	record, ok := s.idempotency[operation+"\n"+key]
	record.ResponseBytes = append([]byte(nil), record.ResponseBytes...)
	return record, ok, nil
}
func (s *MemoryStore) SaveIdempotency(_ context.Context, record ports.IdempotencyRecord) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	identity := record.Operation + "\n" + record.Key
	if existing, ok := s.idempotency[identity]; ok {
		if existing.RequestDigest != record.RequestDigest {
			return model.ErrConflict
		}
		return nil
	}
	record.ResponseBytes = append([]byte(nil), record.ResponseBytes...)
	s.idempotency[identity] = record
	return nil
}
func (s *MemoryStore) Outbox(_ context.Context, limit int) ([]ports.OutboxRecord, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if limit <= 0 || limit > len(s.outbox) {
		limit = len(s.outbox)
	}
	return append([]ports.OutboxRecord(nil), s.outbox[:limit]...), nil
}
func (s *MemoryStore) appendOutbox(p ports.CommitPacket) {
	if p.OutboxType == "" {
		return
	}
	raw, _ := json.Marshal(p.OutboxPayload)
	at := time.Now().UTC()
	if len(p.Events) > 0 {
		at = p.Events[len(p.Events)-1].OccurredAt
	}
	s.outbox = append(s.outbox, ports.OutboxRecord{EventID: p.Unit.ID + ":" + p.OutboxType, EventType: p.OutboxType, AggregateID: p.Unit.ID, Payload: raw, OccurredAt: at})
}
func (s *MemoryStore) Create(_ context.Context, p ports.CommitPacket) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.units[p.Unit.ID]; ok {
		return model.ErrConflict
	}
	s.units[p.Unit.ID] = cloneUnit(p.Unit)
	s.events[p.Unit.ID] = append([]model.Event(nil), p.Events...)
	s.appendOutbox(p)
	return nil
}
func (s *MemoryStore) Append(_ context.Context, expected int64, p ports.CommitPacket) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	u, ok := s.units[p.Unit.ID]
	if !ok {
		return model.ErrNotFound
	}
	if u.LastSequence != expected {
		return model.ErrConflict
	}
	s.units[p.Unit.ID] = cloneUnit(p.Unit)
	s.events[p.Unit.ID] = append(s.events[p.Unit.ID], p.Events...)
	s.appendOutbox(p)
	return nil
}
func (s *MemoryStore) TransitionReceipt(_ context.Context, decisionID, from, to, expectedETag, idempotencyKey, commandDigest, actor, fingerprint string, scope model.CanonicalScope, action string, now time.Time, reason string) (model.AuthorizationReceipt, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for id, u := range s.units {
		if u.Receipt == nil || u.Receipt.DecisionID != decisionID {
			continue
		}
		r := *u.Receipt
		if r.State == to && r.WinnerIdempotencyKey == idempotencyKey && r.WinnerCommandDigest == commandDigest {
			return r, nil
		}
		if r.State != from || r.ETag != expectedETag || r.ETag != model.ReceiptETag(r.ReceiptID, r.Generation) {
			return model.AuthorizationReceipt{}, model.ErrConflict
		}
		if to == model.ReceiptConsumed {
			raw, _ := model.DecodeExact(r.CanonicalBytes)
			var payload model.AuthorityReceiptClaims
			if json.Unmarshal(raw, &payload) != nil || payload.EvidenceFingerprint != fingerprint || !equalScope(payload.Scope, scope) || !model.Contains(payload.Actions, action) || !isCanonicalDigest(commandDigest) || idempotencyKey == "" {
				return model.AuthorizationReceipt{}, model.ErrReceiptMismatch
			}
			expiresAt, parseErr := time.Parse(time.RFC3339Nano, payload.ExpiresAt)
			if parseErr != nil || !now.Before(expiresAt) {
				return model.AuthorizationReceipt{}, model.ErrReceiptExpired
			}
		}
		at := now.UTC()
		r.State = to
		r.PreviousGeneration = r.Generation
		r.Generation++
		r.ETag = model.ReceiptETag(r.ReceiptID, r.Generation)
		r.WinnerIdempotencyKey = idempotencyKey
		r.WinnerCommandDigest = commandDigest
		r.StateActor = actor
		r.StateAt = at.Format(time.RFC3339Nano)
		u.Receipt = &r
		u.LastSequence++
		event, _ := model.NewEvent(u.ID, "state-"+decisionID+"-"+to, "AuthorizationReceipt"+to, actor, u.LastSequence, u.LastHash, map[string]string{"reason": reason}, at)
		u.LastHash = event.Hash
		r.ChainCommit = event.Hash
		u.Receipt = &r
		s.units[id] = u
		s.events[id] = append(s.events[id], event)
		return r, nil
	}
	return model.AuthorizationReceipt{}, model.ErrNotFound
}
func (s *MemoryStore) RecordGitHub(_ context.Context, a model.GitHubApproval) (model.GitHubApproval, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if old, ok := s.github[a.DeliveryID]; ok {
		if old.PayloadDigest != a.PayloadDigest {
			return model.GitHubApproval{}, false, model.ErrConflict
		}
		return old, true, nil
	}
	if a.Approved {
		requested := false
		for _, old := range s.github {
			if old.Requested && old.InstallationID == a.InstallationID && old.Repository == a.Repository && old.RunID == a.RunID && old.RunAttempt == a.RunAttempt && old.HeadSHA == a.HeadSHA && old.CandidateDigest == a.CandidateDigest && old.Environment == a.Environment {
				requested = true
				break
			}
		}
		if !requested {
			return model.GitHubApproval{}, false, model.ErrConflict
		}
	}
	s.github[a.DeliveryID] = a
	return a, false, nil
}

func equalScope(left, right model.CanonicalScope) bool {
	leftRaw, _ := json.Marshal(left)
	rightRaw, _ := json.Marshal(right)
	return string(leftRaw) == string(rightRaw)
}
func isCanonicalDigest(value string) bool {
	if len(value) != 71 || value[:7] != "sha256:" {
		return false
	}
	for _, character := range value[7:] {
		if !(character >= '0' && character <= '9') && !(character >= 'a' && character <= 'f') {
			return false
		}
	}
	return true
}
