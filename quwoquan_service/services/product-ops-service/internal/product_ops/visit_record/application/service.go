package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	visitdomain "quwoquan_service/services/product-ops-service/internal/product_ops/visit_record/domain"
)

const receiptRetention = 180 * 24 * time.Hour
const maxIdempotencyKeyLength = 256

var (
	ErrInvalidInput        = visitdomain.ErrInvalid
	ErrIdempotencyRequired = errors.New("visit idempotency key is required")
	ErrIdempotencyConflict = errors.New("visit idempotency key conflicts with the first command")
)

type RecordVisitCommand = visitdomain.RecordVisitCommand
type VisitRecord = visitdomain.VisitRecord
type VisitStatsQuery = visitdomain.VisitStatsQuery
type VisitStats = visitdomain.VisitStats

// RecordVisitReceipt is the canonical command result exposed by the object
// facade and HTTP adapter. The embedded VisitRecord omits UserID on JSON, so
// no trusted actor identity crosses the boundary.
type RecordVisitReceipt struct {
	VisitRecord
	Replayed bool `json:"replayed"`
}

// CommitCommand is the object-owned atomic persistence packet. ReceiptID never
// contains the caller's raw Idempotency-Key; CommandDigest binds the first key
// use to its actor and target.
type CommitCommand struct {
	Input          RecordVisitCommand
	ReceiptID      string
	CommandDigest  string
	ReceiptExpires time.Time
}

type CommandStore interface {
	CommitVisit(context.Context, CommitCommand) (RecordVisitReceipt, error)
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
	input RecordVisitCommand,
	idempotencyKey string,
) (RecordVisitReceipt, error) {
	input = input.Normalize()
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	if err := input.Validate(); err != nil {
		return RecordVisitReceipt{}, ErrInvalidInput
	}
	if idempotencyKey == "" {
		return RecordVisitReceipt{}, ErrIdempotencyRequired
	}
	if len([]rune(idempotencyKey)) > maxIdempotencyKeyLength {
		return RecordVisitReceipt{}, ErrInvalidInput
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
	query, err := query.NormalizeAndValidate()
	if err != nil {
		return VisitStats{}, ErrInvalidInput
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
