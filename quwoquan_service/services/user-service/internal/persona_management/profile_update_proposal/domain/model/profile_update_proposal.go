package model

import (
	"crypto/sha256"
	"errors"
	"fmt"
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
)

type Status string

const (
	StatusPending   Status = "pending"
	StatusConfirmed Status = "confirmed"
	StatusApplying  Status = "applying"
	StatusApplied   Status = "applied"
	StatusRejected  Status = "rejected"
	StatusExpired   Status = "expired"
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
	Status                       Status                        `json:"status"`
	ReviewedBy                   string                        `json:"reviewedBy,omitempty"`
	TargetPersonaExpectedVersion *int64                        `json:"targetPersonaExpectedVersion,omitempty"`
	Version                      int64                         `json:"version"`
	CreatedAt                    time.Time                     `json:"createdAt"`
	UpdatedAt                    time.Time                     `json:"updatedAt"`
	ResolvedAt                   *time.Time                    `json:"resolvedAt,omitempty"`
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
	now time.Time,
) (ProfileUpdateProposal, []Event, error) {
	proposal := ProfileUpdateProposal{
		ID: id, PersonaID: personaID, Source: source, ProposedChanges: changes,
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
	case StatusPending, StatusConfirmed, StatusApplying, StatusApplied, StatusRejected, StatusExpired:
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
	switch p.Status {
	case StatusPending:
		if p.ReviewedBy != "" || p.TargetPersonaExpectedVersion != nil || p.ResolvedAt != nil {
			return fmt.Errorf("%w: pending proposal cannot contain review or resolution state", ErrInvalidArgument)
		}
	case StatusConfirmed, StatusApplying:
		if strings.TrimSpace(p.ReviewedBy) == "" || p.TargetPersonaExpectedVersion == nil ||
			*p.TargetPersonaExpectedVersion <= 0 || p.ResolvedAt != nil {
			return fmt.Errorf("%w: confirmed or applying proposal requires reviewer and target version without resolution", ErrInvalidArgument)
		}
	case StatusApplied:
		if strings.TrimSpace(p.ReviewedBy) == "" || p.TargetPersonaExpectedVersion == nil ||
			*p.TargetPersonaExpectedVersion <= 0 || p.ResolvedAt == nil {
			return fmt.Errorf("%w: applied proposal requires reviewer, target version and resolvedAt", ErrInvalidArgument)
		}
	case StatusRejected, StatusExpired:
		if strings.TrimSpace(p.ReviewedBy) == "" || p.ResolvedAt == nil {
			return fmt.Errorf("%w: rejected or expired proposal requires reviewer and resolvedAt", ErrInvalidArgument)
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

func (p ProfileUpdateProposal) BeginApply(now time.Time) (ProfileUpdateProposal, []Event, error) {
	if p.Status != StatusConfirmed || p.TargetPersonaExpectedVersion == nil {
		return ProfileUpdateProposal{}, nil, ErrInvalidTransition
	}
	next := p
	next.Status = StatusApplying
	next.Version++
	next.UpdatedAt = now.UTC()
	return next, []Event{next.event("ProfileUpdateProposalApplyStarted", now)}, next.Validate()
}

func (p ProfileUpdateProposal) MarkApplied(now time.Time) (ProfileUpdateProposal, []Event, error) {
	if p.Status != StatusApplying || p.TargetPersonaExpectedVersion == nil {
		return ProfileUpdateProposal{}, nil, ErrInvalidTransition
	}
	next := p
	next.Status = StatusApplied
	next.Version++
	next.UpdatedAt = now.UTC()
	resolvedAt := now.UTC()
	next.ResolvedAt = &resolvedAt
	return next, []Event{next.event("ProfileUpdateProposalApplied", now)}, next.Validate()
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
