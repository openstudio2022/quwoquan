package model

import (
	"crypto/sha256"
	"errors"
	"fmt"
	"slices"
	"sort"
	"strings"
	"time"

	personamodel "quwoquan_service/services/user-service/internal/persona_management/persona/domain/model"
)

var (
	ErrNotFound            = errors.New("profile update proposal not found")
	ErrForbidden           = errors.New("profile update proposal actor is not the target persona")
	ErrVersionConflict     = errors.New("profile update proposal version conflict")
	ErrIdempotencyConflict = errors.New("profile update proposal idempotency conflict")
	ErrInvalidTransition   = errors.New("profile update proposal transition is invalid")
	ErrInvalidArgument     = errors.New("profile update proposal is invalid")
	ErrRollbackExpired     = errors.New("profile update proposal rollback window expired")
)

const DefaultRollbackWindow = 24 * time.Hour

type Status string

const (
	StatusPending     Status = "pending"
	StatusConfirmed   Status = "confirmed"
	StatusApplying    Status = "applying"
	StatusApplied     Status = "applied"
	StatusRollingBack Status = "rolling_back"
	StatusRolledBack  Status = "rolled_back"
	StatusRejected    Status = "rejected"
	StatusExpired     Status = "expired"
)

type Source string

const (
	SourcePersona   Source = "persona"
	SourceAssistant Source = "assistant"
	SourceExternal  Source = "external"
)

type ProfileUpdateProposal struct {
	ID                           string                        `json:"id"`
	PersonaID                    string                        `json:"personaId"`
	Source                       Source                        `json:"source"`
	ProposedChanges              personamodel.ProfileChangeSet `json:"proposedChanges"`
	Reason                       string                        `json:"reason"`
	EvidenceRefs                 []string                      `json:"evidenceRefs"`
	ImpactScope                  []string                      `json:"impactScope"`
	CreatedBy                    string                        `json:"createdBy"`
	CreatedRequestID             string                        `json:"createdRequestId"`
	CreatedTraceID               string                        `json:"createdTraceId"`
	Status                       Status                        `json:"status"`
	ReviewedBy                   string                        `json:"reviewedBy,omitempty"`
	TargetPersonaExpectedVersion *int64                        `json:"targetPersonaExpectedVersion,omitempty"`
	ApplyContext                 *CommandAuditContext          `json:"applyContext,omitempty"`
	ApplyAuditID                 string                        `json:"applyAuditId,omitempty"`
	RollbackDeadline             *time.Time                    `json:"rollbackDeadline,omitempty"`
	RollbackContext              *CommandAuditContext          `json:"rollbackContext,omitempty"`
	RollbackAuditID              string                        `json:"rollbackAuditId,omitempty"`
	Version                      int64                         `json:"version"`
	CreatedAt                    time.Time                     `json:"createdAt"`
	UpdatedAt                    time.Time                     `json:"updatedAt"`
	ResolvedAt                   *time.Time                    `json:"resolvedAt,omitempty"`
}

type CommandAuditContext struct {
	ActorPersonaID string `json:"actorPersonaId"`
	RequestID      string `json:"requestId"`
	TraceID        string `json:"traceId"`
}

func NewCommandAuditContext(actorPersonaID, requestID, traceID string) (CommandAuditContext, error) {
	context := CommandAuditContext{
		ActorPersonaID: strings.TrimSpace(actorPersonaID),
		RequestID:      strings.TrimSpace(requestID),
		TraceID:        strings.TrimSpace(traceID),
	}
	if err := context.Validate(); err != nil {
		return CommandAuditContext{}, err
	}
	return context, nil
}

func (c CommandAuditContext) Validate() error {
	if c.ActorPersonaID == "" || c.RequestID == "" || c.TraceID == "" ||
		len(c.ActorPersonaID) > 96 || len(c.RequestID) > 128 || len(c.TraceID) > 128 {
		return fmt.Errorf("%w: actor, requestId and traceId are required within persistence limits", ErrInvalidArgument)
	}
	return nil
}

type AuditAction string

const (
	AuditActionApply    AuditAction = "apply"
	AuditActionRollback AuditAction = "rollback"
)

type AuditRecord struct {
	ID               string                       `json:"id"`
	ProposalID       string                       `json:"proposalId"`
	Action           AuditAction                  `json:"action"`
	Context          CommandAuditContext          `json:"context"`
	Before           personamodel.ProfileSnapshot `json:"before"`
	After            personamodel.ProfileSnapshot `json:"after"`
	OccurredAt       time.Time                    `json:"occurredAt"`
	RollbackDeadline *time.Time                   `json:"rollbackDeadline,omitempty"`
}

func NewAuditRecord(
	proposalID string,
	action AuditAction,
	context CommandAuditContext,
	before personamodel.ProfileSnapshot,
	after personamodel.ProfileSnapshot,
	occurredAt time.Time,
	rollbackDeadline *time.Time,
) (AuditRecord, error) {
	digest := sha256.Sum256([]byte(string(action) + "\x00" + strings.TrimSpace(proposalID)))
	record := AuditRecord{
		ID:         fmt.Sprintf("profile-proposal-audit-%x", digest[:16]),
		ProposalID: strings.TrimSpace(proposalID),
		Action:     action,
		Context:    context,
		Before:     before,
		After:      after,
		OccurredAt: occurredAt.UTC(),
	}
	if rollbackDeadline != nil {
		deadline := rollbackDeadline.UTC()
		record.RollbackDeadline = &deadline
	}
	if err := record.Validate(); err != nil {
		return AuditRecord{}, err
	}
	return record, nil
}

func (a AuditRecord) Validate() error {
	if a.ID == "" || len(a.ID) > 96 || a.ProposalID == "" || len(a.ProposalID) > 64 ||
		a.OccurredAt.IsZero() || a.Before.Version <= 0 || a.After.Version <= 0 {
		return fmt.Errorf("%w: audit identity, versions and timestamp are required", ErrInvalidArgument)
	}
	if err := a.Context.Validate(); err != nil {
		return err
	}
	switch a.Action {
	case AuditActionApply:
		if a.After.Version != a.Before.Version+1 || a.RollbackDeadline == nil ||
			!a.RollbackDeadline.After(a.OccurredAt) {
			return fmt.Errorf("%w: apply audit requires adjacent versions and rollback deadline", ErrInvalidArgument)
		}
	case AuditActionRollback:
		if a.After.Version != a.Before.Version+1 || a.RollbackDeadline != nil {
			return fmt.Errorf("%w: rollback audit requires adjacent versions without deadline", ErrInvalidArgument)
		}
	default:
		return fmt.Errorf("%w: unknown audit action %q", ErrInvalidArgument, a.Action)
	}
	return nil
}

type Event struct {
	ID               string
	Type             string
	AggregateID      string
	AggregateVersion int64
	OccurredAt       time.Time
}

func NewProfileUpdateProposal(
	id string,
	personaID string,
	source Source,
	changes personamodel.ProfileChangeSet,
	reason string,
	evidenceRefs []string,
	impactScope []string,
	creationContext CommandAuditContext,
	now time.Time,
) (ProfileUpdateProposal, []Event, error) {
	canonicalEvidence, err := canonicalStringSet(evidenceRefs, 16, 192, "evidenceRefs")
	if err != nil {
		return ProfileUpdateProposal{}, nil, err
	}
	if err := validateEvidenceRefs(canonicalEvidence); err != nil {
		return ProfileUpdateProposal{}, nil, err
	}
	canonicalImpact, err := canonicalStringSet(impactScope, 7, 32, "impactScope")
	if err != nil {
		return ProfileUpdateProposal{}, nil, err
	}
	proposal := ProfileUpdateProposal{
		ID: id, PersonaID: personaID, Source: source, ProposedChanges: changes,
		Reason: strings.TrimSpace(reason), EvidenceRefs: canonicalEvidence,
		ImpactScope: canonicalImpact, CreatedBy: creationContext.ActorPersonaID,
		CreatedRequestID: creationContext.RequestID, CreatedTraceID: creationContext.TraceID,
		Status: StatusPending, Version: 1, CreatedAt: now.UTC(), UpdatedAt: now.UTC(),
	}
	if err := proposal.Validate(); err != nil {
		return ProfileUpdateProposal{}, nil, err
	}
	return proposal, []Event{proposal.event("ProfileUpdateProposalCreated", now)}, nil
}

func (p ProfileUpdateProposal) Validate() error {
	if strings.TrimSpace(p.ID) == "" || strings.TrimSpace(p.PersonaID) == "" {
		return fmt.Errorf("%w: proposal id and personaId are required", ErrInvalidArgument)
	}
	if len(p.ID) > 64 || len(p.PersonaID) > 96 {
		return fmt.Errorf("%w: proposal id or personaId exceeds persistence limit", ErrInvalidArgument)
	}
	switch p.Source {
	case SourcePersona, SourceAssistant, SourceExternal:
	default:
		return fmt.Errorf("%w: unknown proposal source %q", ErrInvalidArgument, p.Source)
	}
	switch p.Status {
	case StatusPending, StatusConfirmed, StatusApplying, StatusApplied,
		StatusRollingBack, StatusRolledBack, StatusRejected, StatusExpired:
	default:
		return fmt.Errorf("%w: unknown proposal status %q", ErrInvalidArgument, p.Status)
	}
	if p.Version <= 0 || p.CreatedAt.IsZero() || p.UpdatedAt.IsZero() {
		return fmt.Errorf("%w: proposal version and timestamps are required", ErrInvalidArgument)
	}
	if p.UpdatedAt.Before(p.CreatedAt) {
		return fmt.Errorf("%w: proposal updatedAt cannot precede createdAt", ErrInvalidArgument)
	}
	if err := p.ProposedChanges.Validate(); err != nil {
		return err
	}
	if strings.TrimSpace(p.Reason) == "" || len([]rune(strings.TrimSpace(p.Reason))) > 1000 {
		return fmt.Errorf("%w: reason must contain 1..1000 characters", ErrInvalidArgument)
	}
	evidenceRefs, err := canonicalStringSet(p.EvidenceRefs, 16, 192, "evidenceRefs")
	if err != nil || !slices.Equal(evidenceRefs, p.EvidenceRefs) {
		return fmt.Errorf("%w: evidenceRefs must be canonical: %v", ErrInvalidArgument, err)
	}
	if err := validateEvidenceRefs(evidenceRefs); err != nil {
		return err
	}
	impactScope, err := canonicalStringSet(p.ImpactScope, 7, 32, "impactScope")
	if err != nil || !slices.Equal(impactScope, p.ImpactScope) ||
		!slices.Equal(impactScope, p.ProposedChanges.ChangedFields()) {
		return fmt.Errorf("%w: impactScope must exactly match proposedChanges", ErrInvalidArgument)
	}
	creationContext := CommandAuditContext{
		ActorPersonaID: strings.TrimSpace(p.CreatedBy),
		RequestID:      strings.TrimSpace(p.CreatedRequestID),
		TraceID:        strings.TrimSpace(p.CreatedTraceID),
	}
	if err := creationContext.Validate(); err != nil {
		return err
	}
	switch p.Status {
	case StatusPending:
		if p.ReviewedBy != "" || p.TargetPersonaExpectedVersion != nil || p.ResolvedAt != nil ||
			p.ApplyContext != nil || p.ApplyAuditID != "" || p.RollbackDeadline != nil ||
			p.RollbackContext != nil || p.RollbackAuditID != "" {
			return fmt.Errorf("%w: pending proposal cannot contain review or resolution state", ErrInvalidArgument)
		}
	case StatusConfirmed:
		if strings.TrimSpace(p.ReviewedBy) == "" || p.TargetPersonaExpectedVersion == nil ||
			*p.TargetPersonaExpectedVersion <= 0 || p.ResolvedAt != nil || p.ApplyContext != nil ||
			p.ApplyAuditID != "" || p.RollbackDeadline != nil || p.RollbackContext != nil ||
			p.RollbackAuditID != "" {
			return fmt.Errorf("%w: confirmed proposal has invalid review/apply state", ErrInvalidArgument)
		}
	case StatusApplying:
		if strings.TrimSpace(p.ReviewedBy) == "" || p.TargetPersonaExpectedVersion == nil ||
			*p.TargetPersonaExpectedVersion <= 0 || p.ResolvedAt != nil || p.ApplyContext == nil ||
			p.ApplyAuditID != "" || p.RollbackDeadline != nil || p.RollbackContext != nil ||
			p.RollbackAuditID != "" || p.ApplyContext.Validate() != nil {
			return fmt.Errorf("%w: applying proposal requires trusted apply context", ErrInvalidArgument)
		}
	case StatusApplied:
		if strings.TrimSpace(p.ReviewedBy) == "" || p.TargetPersonaExpectedVersion == nil ||
			*p.TargetPersonaExpectedVersion <= 0 || p.ResolvedAt == nil || p.ApplyContext == nil ||
			p.ApplyContext.Validate() != nil || strings.TrimSpace(p.ApplyAuditID) == "" ||
			p.RollbackDeadline == nil || !p.RollbackDeadline.After(*p.ResolvedAt) ||
			p.RollbackContext != nil || p.RollbackAuditID != "" {
			return fmt.Errorf("%w: applied proposal requires apply audit and rollback deadline", ErrInvalidArgument)
		}
	case StatusRollingBack:
		if strings.TrimSpace(p.ReviewedBy) == "" || p.TargetPersonaExpectedVersion == nil ||
			p.ResolvedAt == nil || p.ApplyContext == nil || p.ApplyContext.Validate() != nil ||
			p.ApplyAuditID == "" || p.RollbackDeadline == nil || p.RollbackContext == nil ||
			p.RollbackContext.Validate() != nil || p.RollbackAuditID != "" {
			return fmt.Errorf("%w: rolling_back proposal requires apply audit and trusted rollback context", ErrInvalidArgument)
		}
	case StatusRolledBack:
		if strings.TrimSpace(p.ReviewedBy) == "" || p.TargetPersonaExpectedVersion == nil ||
			p.ResolvedAt == nil || p.ApplyContext == nil || p.ApplyContext.Validate() != nil ||
			p.ApplyAuditID == "" || p.RollbackDeadline == nil || p.RollbackContext == nil ||
			p.RollbackContext.Validate() != nil || p.RollbackAuditID == "" {
			return fmt.Errorf("%w: rolled_back proposal requires immutable apply and rollback audits", ErrInvalidArgument)
		}
	case StatusRejected, StatusExpired:
		if strings.TrimSpace(p.ReviewedBy) == "" || p.ResolvedAt == nil {
			return fmt.Errorf("%w: rejected or expired proposal requires reviewer and resolvedAt", ErrInvalidArgument)
		}
	}
	return nil
}

func canonicalStringSet(values []string, maxItems, maxLength int, field string) ([]string, error) {
	if len(values) == 0 || len(values) > maxItems {
		return nil, fmt.Errorf("%w: %s must contain 1..%d items", ErrInvalidArgument, field, maxItems)
	}
	unique := make(map[string]struct{}, len(values))
	for _, raw := range values {
		value := strings.TrimSpace(raw)
		if value == "" || len(value) > maxLength {
			return nil, fmt.Errorf("%w: %s item is empty or too long", ErrInvalidArgument, field)
		}
		unique[value] = struct{}{}
	}
	result := make([]string, 0, len(unique))
	for value := range unique {
		result = append(result, value)
	}
	sort.Strings(result)
	return result, nil
}

func validateEvidenceRefs(values []string) error {
	for _, value := range values {
		kind, id, found := strings.Cut(value, ":")
		if !found || strings.TrimSpace(kind) == "" || strings.TrimSpace(id) == "" ||
			strings.ContainsAny(value, " \t\r\n") {
			return fmt.Errorf("%w: evidenceRefs must use typed kind:id references", ErrInvalidArgument)
		}
	}
	return nil
}

func (p ProfileUpdateProposal) Confirm(
	reviewerPersonaID string,
	targetPersonaExpectedVersion int64,
	now time.Time,
) (ProfileUpdateProposal, []Event, error) {
	if p.Status != StatusPending || targetPersonaExpectedVersion <= 0 {
		return ProfileUpdateProposal{}, nil, ErrInvalidTransition
	}
	next := p
	next.Status = StatusConfirmed
	next.ReviewedBy = strings.TrimSpace(reviewerPersonaID)
	next.TargetPersonaExpectedVersion = &targetPersonaExpectedVersion
	next.Version++
	next.UpdatedAt = now.UTC()
	if err := next.Validate(); err != nil {
		return ProfileUpdateProposal{}, nil, err
	}
	return next, []Event{next.event("ProfileUpdateProposalConfirmed", now)}, nil
}

func (p ProfileUpdateProposal) BeginApply(
	context CommandAuditContext,
	now time.Time,
) (ProfileUpdateProposal, []Event, error) {
	if p.Status != StatusConfirmed || p.TargetPersonaExpectedVersion == nil ||
		context.ActorPersonaID != p.PersonaID {
		return ProfileUpdateProposal{}, nil, ErrInvalidTransition
	}
	if err := context.Validate(); err != nil {
		return ProfileUpdateProposal{}, nil, err
	}
	next := p
	next.Status = StatusApplying
	next.ApplyContext = &context
	next.Version++
	next.UpdatedAt = now.UTC()
	return next, []Event{next.event("ProfileUpdateProposalApplyStarted", now)}, next.Validate()
}

func (p ProfileUpdateProposal) MarkApplied(
	auditID string,
	rollbackDeadline time.Time,
	now time.Time,
) (ProfileUpdateProposal, []Event, error) {
	if p.Status != StatusApplying || p.TargetPersonaExpectedVersion == nil ||
		strings.TrimSpace(auditID) == "" || !rollbackDeadline.After(now) {
		return ProfileUpdateProposal{}, nil, ErrInvalidTransition
	}
	next := p
	next.Status = StatusApplied
	next.ApplyAuditID = strings.TrimSpace(auditID)
	deadline := rollbackDeadline.UTC()
	next.RollbackDeadline = &deadline
	next.Version++
	next.UpdatedAt = now.UTC()
	resolvedAt := now.UTC()
	next.ResolvedAt = &resolvedAt
	return next, []Event{next.event("ProfileUpdateProposalApplied", now)}, next.Validate()
}

func (p ProfileUpdateProposal) BeginRollback(
	context CommandAuditContext,
	now time.Time,
) (ProfileUpdateProposal, []Event, error) {
	if p.Status != StatusApplied || p.RollbackDeadline == nil ||
		context.ActorPersonaID != p.PersonaID {
		return ProfileUpdateProposal{}, nil, ErrInvalidTransition
	}
	if now.UTC().After(p.RollbackDeadline.UTC()) {
		return ProfileUpdateProposal{}, nil, ErrRollbackExpired
	}
	if err := context.Validate(); err != nil {
		return ProfileUpdateProposal{}, nil, err
	}
	next := p
	next.Status = StatusRollingBack
	next.RollbackContext = &context
	next.Version++
	next.UpdatedAt = now.UTC()
	return next, []Event{next.event("ProfileUpdateProposalRollbackStarted", now)}, next.Validate()
}

func (p ProfileUpdateProposal) AbortRollback(now time.Time) (ProfileUpdateProposal, []Event, error) {
	if p.Status != StatusRollingBack {
		return ProfileUpdateProposal{}, nil, ErrInvalidTransition
	}
	next := p
	next.Status = StatusApplied
	next.RollbackContext = nil
	next.Version++
	next.UpdatedAt = now.UTC()
	return next, []Event{next.event("ProfileUpdateProposalRollbackAborted", now)}, next.Validate()
}

func (p ProfileUpdateProposal) MarkRolledBack(
	auditID string,
	now time.Time,
) (ProfileUpdateProposal, []Event, error) {
	if p.Status != StatusRollingBack || strings.TrimSpace(auditID) == "" {
		return ProfileUpdateProposal{}, nil, ErrInvalidTransition
	}
	next := p
	next.Status = StatusRolledBack
	next.RollbackAuditID = strings.TrimSpace(auditID)
	next.Version++
	next.UpdatedAt = now.UTC()
	resolvedAt := now.UTC()
	next.ResolvedAt = &resolvedAt
	return next, []Event{next.event("ProfileUpdateProposalRolledBack", now)}, next.Validate()
}

func (p ProfileUpdateProposal) ExpireApply(now time.Time) (ProfileUpdateProposal, []Event, error) {
	if p.Status != StatusApplying {
		return ProfileUpdateProposal{}, nil, ErrInvalidTransition
	}
	next := p
	next.Status = StatusExpired
	next.Version++
	next.UpdatedAt = now.UTC()
	resolvedAt := now.UTC()
	next.ResolvedAt = &resolvedAt
	return next, []Event{next.event("ProfileUpdateProposalExpired", now)}, next.Validate()
}

func (p ProfileUpdateProposal) Reject(reviewerPersonaID string, now time.Time) (ProfileUpdateProposal, []Event, error) {
	if p.Status != StatusPending && p.Status != StatusConfirmed {
		return ProfileUpdateProposal{}, nil, ErrInvalidTransition
	}
	next := p
	next.Status = StatusRejected
	next.ReviewedBy = strings.TrimSpace(reviewerPersonaID)
	next.Version++
	next.UpdatedAt = now.UTC()
	resolvedAt := now.UTC()
	next.ResolvedAt = &resolvedAt
	return next, []Event{next.event("ProfileUpdateProposalRejected", now)}, next.Validate()
}

func (p ProfileUpdateProposal) event(eventType string, now time.Time) Event {
	eventDigest := sha256.Sum256([]byte(fmt.Sprintf("%s\x00%d\x00%s", p.ID, p.Version, eventType)))
	return Event{
		ID:   fmt.Sprintf("profile-proposal-event-%x", eventDigest[:16]),
		Type: eventType, AggregateID: p.ID, AggregateVersion: p.Version,
		OccurredAt: now.UTC(),
	}
}
