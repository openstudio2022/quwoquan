package application

import (
	"context"
	"errors"
	"strings"
)

type VisitInput struct {
	UserID     string `json:"userId"`
	TargetType string `json:"targetType"`
	TargetKey  string `json:"targetKey"`
	SessionID  string `json:"sessionId,omitempty"`
	Source     string `json:"source,omitempty"`
}

type VisitRecord struct {
	TargetType string `json:"targetType" bson:"targetType"`
	TargetKey  string `json:"targetKey" bson:"targetKey"`
	UserID     string `json:"userId" bson:"userId"`
	VisitCount int    `json:"visitCount" bson:"visitCount"`
	LastSeenAt string `json:"lastSeenAt,omitempty" bson:"lastSeenAt,omitempty"`
	SessionID  string `json:"sessionId,omitempty" bson:"sessionId,omitempty"`
	Source     string `json:"source,omitempty" bson:"source,omitempty"`
}

type VisitStatsQuery struct{ TargetType, TargetKey string }

type VisitStats struct {
	TotalVisits int           `json:"totalVisits"`
	Items       []VisitRecord `json:"items"`
}

type CommandResult struct {
	VisitRecord
	Replayed bool `json:"replayed,omitempty"`
}

type Store interface {
	RecordVisit(context.Context, VisitInput) (VisitRecord, error)
	GetVisit(ctx context.Context, userID, targetType, targetKey string) (VisitRecord, bool, error)
	GetVisitStats(context.Context, VisitStatsQuery) (VisitStats, error)
}

type LedgerState string

const (
	LedgerNew      LedgerState = "new"
	LedgerPending  LedgerState = "pending"
	LedgerAccepted LedgerState = "accepted"
)

type Ledger interface {
	Begin(context.Context, string, int) (LedgerState, error)
	MarkAccepted(context.Context, string, int) error
}

var ErrIdempotencyKeyRequired = errors.New("visit idempotency key is required")

type Service struct {
	store  Store
	ledger Ledger
}

func NewService(store Store, ledger Ledger) *Service {
	return &Service{store: store, ledger: ledger}
}

func (s *Service) RecordVisit(ctx context.Context, input VisitInput, idempotencyKey string) (CommandResult, error) {
	input.TargetType = strings.TrimSpace(input.TargetType)
	input.TargetKey = strings.TrimSpace(input.TargetKey)
	input.UserID = strings.TrimSpace(input.UserID)
	if input.UserID == "" {
		input.UserID = "anonymous"
	}
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	if idempotencyKey == "" {
		return CommandResult{}, ErrIdempotencyKeyRequired
	}
	dedupeKey := "visit:" + input.UserID + ":" + idempotencyKey
	state, err := s.ledger.Begin(ctx, dedupeKey, 1)
	if err != nil {
		return CommandResult{}, err
	}
	if state == LedgerAccepted {
		record, found, err := s.store.GetVisit(ctx, input.UserID, input.TargetType, input.TargetKey)
		if err != nil {
			return CommandResult{}, err
		}
		if found {
			return CommandResult{VisitRecord: record, Replayed: true}, nil
		}
	}
	record, err := s.store.RecordVisit(ctx, input)
	if err != nil {
		return CommandResult{}, err
	}
	if err := s.ledger.MarkAccepted(ctx, dedupeKey, 1); err != nil {
		return CommandResult{}, err
	}
	return CommandResult{VisitRecord: record}, nil
}

func (s *Service) GetVisitStats(ctx context.Context, query VisitStatsQuery) (VisitStats, error) {
	return s.store.GetVisitStats(ctx, query)
}
