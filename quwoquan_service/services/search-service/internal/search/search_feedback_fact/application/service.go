package application

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"strings"
	"time"

	signalapplication "quwoquan_service/services/search-service/internal/search/recommendation_signal_fact/application"
)

// Event is the authoritative SearchFeedbackEvent append payload after actor
// identity has been derived from verified transport context.
type Event struct {
	SearchRequestID string `json:"searchRequestId"`
	ViewerID        string `json:"-"`
	EventType       string `json:"eventType"`
	ObjectID        string `json:"objectId,omitempty"`
	Target          string `json:"target,omitempty"`
	RankPosition    int    `json:"rankPosition,omitempty"`
	ReferralSource  string `json:"referralSource,omitempty"`
	FeedRequestID   string `json:"feedRequestId,omitempty"`
	DwellMs         int    `json:"dwellMs,omitempty"`
}

type CommandMeta struct {
	IdempotencyKey string
	CommandDigest  string
}

var (
	ErrInvalid             = errors.New("invalid search feedback")
	ErrUnavailable         = errors.New("search feedback sink unavailable")
	ErrIdempotencyConflict = errors.New("search feedback idempotency conflict")
)

type Sink interface {
	Record(ctx context.Context, event Event, meta CommandMeta) error
}

type Observer interface {
	ObserveFeedback(eventType string)
}

type Service struct {
	sink Sink
}

func NewService(sink Sink) *Service {
	return &Service{sink: sink}
}

// Report transactionally persists the command receipt, semantic fact, and—when
// applicable—an independent signal-delivery row. The relay acknowledges only
// that mutable row, so a feedback fact is never rewritten after commit.
func (s *Service) Report(
	ctx context.Context,
	event Event,
	meta CommandMeta,
) error {
	event = normalize(event)
	meta.IdempotencyKey = strings.TrimSpace(meta.IdempotencyKey)
	meta.CommandDigest = strings.TrimSpace(meta.CommandDigest)
	if err := validate(event, meta); err != nil {
		return err
	}
	if s == nil || s.sink == nil {
		return ErrUnavailable
	}
	if err := s.sink.Record(ctx, event, meta); err != nil {
		return err
	}
	return nil
}

func normalize(event Event) Event {
	event.SearchRequestID = strings.TrimSpace(event.SearchRequestID)
	event.ViewerID = strings.TrimSpace(event.ViewerID)
	event.EventType = strings.TrimSpace(event.EventType)
	event.ObjectID = strings.TrimSpace(event.ObjectID)
	event.Target = strings.TrimSpace(event.Target)
	event.ReferralSource = strings.TrimSpace(event.ReferralSource)
	event.FeedRequestID = strings.TrimSpace(event.FeedRequestID)
	return event
}

// RecommendationSignal returns the stable downstream signal represented by a
// committed feedback fact. Non-click facts deliberately produce no signal.
func RecommendationSignal(
	event Event,
	createdAt time.Time,
) (signalapplication.Signal, bool) {
	event = normalize(event)
	if event.EventType != "click" ||
		event.SearchRequestID == "" ||
		event.ObjectID == "" {
		return signalapplication.Signal{}, false
	}
	if createdAt.IsZero() {
		return signalapplication.Signal{}, false
	}
	semanticKey := strings.Join(
		[]string{event.SearchRequestID, event.EventType, event.ObjectID},
		"\x00",
	)
	return signalapplication.Signal{
		SignalID: fmt.Sprintf(
			"feedback:%x",
			sha256.Sum256([]byte(semanticKey)),
		),
		SignalType:       "click",
		SearchRequestID:  event.SearchRequestID,
		UserID:           event.ViewerID,
		EngagedObjectIDs: []string{event.ObjectID},
		CreatedAt:        createdAt.UTC(),
	}, true
}

func validate(event Event, meta CommandMeta) error {
	if event.SearchRequestID == "" || len(event.SearchRequestID) > 128 {
		return fmt.Errorf("%w: searchRequestId is required and must be at most 128 characters", ErrInvalid)
	}
	switch event.EventType {
	case "impression", "click", "dwell", "refine", "zero_result", "degrade":
	default:
		return fmt.Errorf("%w: unsupported eventType", ErrInvalid)
	}
	if event.EventType == "click" &&
		(event.ObjectID == "" || event.Target == "" || event.RankPosition <= 0) {
		return fmt.Errorf("%w: click requires objectId, target and positive rankPosition", ErrInvalid)
	}
	if event.RankPosition < 0 {
		return fmt.Errorf("%w: rankPosition must not be negative", ErrInvalid)
	}
	if event.EventType == "dwell" && event.DwellMs <= 0 {
		return fmt.Errorf("%w: dwell requires positive dwellMs", ErrInvalid)
	}
	if event.EventType != "dwell" && event.DwellMs != 0 {
		return fmt.Errorf("%w: only dwell may include dwellMs", ErrInvalid)
	}
	if meta.IdempotencyKey == "" || meta.CommandDigest == "" {
		return fmt.Errorf("%w: idempotency metadata is required", ErrInvalid)
	}
	return nil
}
