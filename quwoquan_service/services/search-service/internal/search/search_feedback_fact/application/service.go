package application

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"strings"
	"time"

	signalapplication "quwoquan_service/services/search-service/internal/search/recommendation_signal_fact/application"
	feedbackdomain "quwoquan_service/services/search-service/internal/search/search_feedback_fact/domain"
)

// Event is the authoritative SearchFeedbackEvent append payload after actor
// identity has been derived from verified transport context.
type Event = feedbackdomain.Event

type CommandMeta struct {
	IdempotencyKey string
	CommandDigest  string
}

var (
	ErrInvalid             = feedbackdomain.ErrInvalid
	ErrUnavailable         = errors.New("search feedback sink unavailable")
	ErrIdempotencyConflict = errors.New("search feedback idempotency conflict")
)

type Sink interface {
	Record(ctx context.Context, event Event, meta CommandMeta) error
}

// HeatFeedback is the privacy-minimized SearchFeedbackFact projection exposed
// to the SearchTermHeatView builder. Collection access remains object-local.
type HeatFeedback struct {
	SearchRequestID string
	EventType       string
	ObjectID        string
	CreatedAt       time.Time
}

type HeatReader interface {
	ListHeatFeedback(
		ctx context.Context,
		since time.Time,
		limit int64,
	) ([]HeatFeedback, error)
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
	return event.Normalize()
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
	if err := event.Validate(); err != nil {
		return err
	}
	if meta.IdempotencyKey == "" || meta.CommandDigest == "" {
		return fmt.Errorf("%w: idempotency metadata is required", ErrInvalid)
	}
	return nil
}
