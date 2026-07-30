package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"
)

const receiptRetention = 180 * 24 * time.Hour

var (
	ErrInvalidInput        = errors.New("invalid visit input")
	ErrIdempotencyRequired = errors.New("visit idempotency key is required")
	ErrIdempotencyConflict = errors.New("visit idempotency key conflicts with the first command")
)

var supportedTargetTypes = map[string]struct{}{
	"page":   {},
	"post":   {},
	"circle": {},
	"user":   {},
}

type VisitInput struct {
	UserID     string `json:"userId"`
	TargetType string `json:"targetType"`
	TargetKey  string `json:"targetKey"`
}

type VisitRecord struct {
	TargetType string    `json:"targetType" bson:"targetType"`
	TargetKey  string    `json:"targetKey" bson:"targetKey"`
	UserID     string    `json:"-" bson:"userId"`
	VisitCount int       `json:"visitCount" bson:"visitCount"`
	OccurredAt time.Time `json:"occurredAt" bson:"occurredAt"`
}

type VisitStatsQuery struct {
	TargetType string
	TargetKey  string
}

type VisitStats struct {
	TotalVisits int           `json:"totalVisits"`
	Items       []VisitRecord `json:"items"`
}

type CommandResult struct {
	VisitRecord
	Replayed bool `json:"replayed,omitempty"`
}

// CommitCommand is the object-owned atomic persistence packet. ReceiptID never
// contains the caller's raw Idempotency-Key; CommandDigest binds the first key
// use to its actor and target.
type CommitCommand struct {
	Input          VisitInput
	ReceiptID      string
	CommandDigest  string
	ReceiptExpires time.Time
}

type CommandStore interface {
	CommitVisit(context.Context, CommitCommand) (CommandResult, error)
}

type StatsReader interface {
	GetVisitStats(context.Context, VisitStatsQuery) (VisitStats, error)
}

type Store interface {
	CommandStore
	StatsReader
}

type Service struct {
	store Store
	now   func() time.Time
}

func NewService(store Store) *Service {
	if store == nil {
		panic("visit record service requires store")
	}
	return &Service{store: store, now: time.Now}
}

func (s *Service) RecordVisit(
	ctx context.Context,
	input VisitInput,
	idempotencyKey string,
) (CommandResult, error) {
	input.UserID = strings.TrimSpace(input.UserID)
	input.TargetType = strings.TrimSpace(input.TargetType)
	input.TargetKey = strings.TrimSpace(input.TargetKey)
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	if input.UserID == "" || input.TargetKey == "" || len(input.TargetKey) > 256 {
		return CommandResult{}, ErrInvalidInput
	}
	if _, supported := supportedTargetTypes[input.TargetType]; !supported {
		return CommandResult{}, ErrInvalidInput
	}
	if idempotencyKey == "" {
		return CommandResult{}, ErrIdempotencyRequired
	}

	receiptID := digest(struct {
		Namespace string `json:"namespace"`
		UserID    string `json:"userId"`
		Key       string `json:"key"`
	}{Namespace: "visit_record", UserID: input.UserID, Key: idempotencyKey})
	commandDigest := digest(struct {
		UserID     string `json:"userId"`
		TargetType string `json:"targetType"`
		TargetKey  string `json:"targetKey"`
	}{UserID: input.UserID, TargetType: input.TargetType, TargetKey: input.TargetKey})

	return s.store.CommitVisit(ctx, CommitCommand{
		Input:          input,
		ReceiptID:      receiptID,
		CommandDigest:  commandDigest,
		ReceiptExpires: s.now().UTC().Add(receiptRetention),
	})
}

func (s *Service) GetVisitStats(
	ctx context.Context,
	query VisitStatsQuery,
) (VisitStats, error) {
	query.TargetType = strings.TrimSpace(query.TargetType)
	query.TargetKey = strings.TrimSpace(query.TargetKey)
	if query.TargetType != "" {
		if _, supported := supportedTargetTypes[query.TargetType]; !supported {
			return VisitStats{}, ErrInvalidInput
		}
	}
	return s.store.GetVisitStats(ctx, query)
}

func digest(value any) string {
	canonical, err := json.Marshal(value)
	if err != nil {
		panic(err)
	}
	sum := sha256.Sum256(canonical)
	return hex.EncodeToString(sum[:])
}
