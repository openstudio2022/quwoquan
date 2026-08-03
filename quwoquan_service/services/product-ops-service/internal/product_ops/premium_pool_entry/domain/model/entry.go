package model

import (
	"errors"
	"strings"
	"time"
)

type Status string

const (
	StatusActive          Status = "active"
	StatusRolledBack      Status = "rolled_back"
	StatusTakedownEjected Status = "takedown_ejected"
	MinimumQualityScore          = 0.75
)

var (
	ErrInvalidArgument      = errors.New("premium pool entry invalid argument")
	ErrNotFound             = errors.New("premium pool entry not found")
	ErrInvalidTransition    = errors.New("premium pool entry invalid transition")
	ErrRevisionConflict     = errors.New("premium pool entry revision conflict")
	ErrIdempotencyConflict  = errors.New("premium pool entry idempotency conflict")
	ErrDualApprovalRequired = errors.New("premium pool entry requires two distinct approvals")
)

type Entry struct {
	ContentID        string
	Scope            string
	Status           Status
	QualityScore     float64
	QualityAdmission string
	SupplySource     string
	SourceTaskID     string
	AuditID          string
	RollbackToken    string
	FeaturedAt       time.Time
	ExpiresAt        time.Time
	Revision         int64
	UpdatedAt        time.Time
}

type UpsertInput struct {
	ContentID        string
	Scope            string
	QualityScore     float64
	QualityAdmission string
	SupplySource     string
	SourceTaskID     string
	AuditID          string
	RollbackToken    string
	ExpiresAt        time.Time
}

func Upsert(current *Entry, input UpsertInput, now time.Time) (Entry, error) {
	now = now.UTC()
	contentID := strings.TrimSpace(input.ContentID)
	if contentID == "" {
		return Entry{}, ErrInvalidArgument
	}
	scope := strings.ToLower(strings.TrimSpace(input.Scope))
	if scope == "" {
		scope = "global"
	}
	if scope != "global" ||
		strings.ToLower(strings.TrimSpace(input.QualityAdmission)) != "approved" ||
		input.QualityScore < MinimumQualityScore ||
		strings.TrimSpace(input.AuditID) == "" ||
		input.ExpiresAt.IsZero() || !input.ExpiresAt.After(now) {
		return Entry{}, ErrInvalidArgument
	}
	if current != nil && strings.TrimSpace(current.ContentID) != contentID {
		return Entry{}, ErrInvalidArgument
	}
	rollbackToken := strings.TrimSpace(input.RollbackToken)
	if rollbackToken == "" {
		rollbackToken = "rbk-premium-" + contentID
	}
	revision := int64(1)
	if current != nil {
		revision = current.Revision + 1
	}
	return Entry{
		ContentID: contentID, Scope: scope, Status: StatusActive,
		QualityScore: input.QualityScore, QualityAdmission: "approved",
		SupplySource: strings.TrimSpace(input.SupplySource),
		SourceTaskID: strings.TrimSpace(input.SourceTaskID),
		AuditID:      strings.TrimSpace(input.AuditID), RollbackToken: rollbackToken,
		FeaturedAt: now, ExpiresAt: input.ExpiresAt.UTC(), Revision: revision,
		UpdatedAt: now,
	}, nil
}

func (entry Entry) Rollback(now time.Time) (Entry, error) {
	if entry.Status != StatusActive || entry.Revision <= 0 {
		return Entry{}, ErrInvalidTransition
	}
	entry.Status = StatusRolledBack
	entry.Revision++
	entry.UpdatedAt = now.UTC()
	return entry, nil
}

func (entry Entry) Takedown(now time.Time) (Entry, error) {
	if entry.Status != StatusActive || entry.Revision <= 0 {
		return Entry{}, ErrInvalidTransition
	}
	entry.Status = StatusTakedownEjected
	entry.Revision++
	entry.UpdatedAt = now.UTC()
	return entry, nil
}

func (entry Entry) ActiveAt(now time.Time) bool {
	return entry.Status == StatusActive && entry.ExpiresAt.After(now.UTC())
}

func (entry Entry) TakedownEjected() bool {
	return entry.Status == StatusTakedownEjected
}
