// Package searchindex implements the circle domain's write side of the unified
// search index (the circle.search_index_worker module). A write-time projector
// keeps the shared ES/OpenSearch index in sync with circle lifecycle events, and
// a backfill entry point rebuilds the index from the live store for cold start.
//
// It is a pure producer: it never serves queries. The circle→Document projection
// is owned by application.ProjectCircleToSearchDocument (single source of truth,
// shared with the native SearchCircles surface) and the ES document shape is
// owned by runtime/search/es. This package only decides which lifecycle events
// upsert vs delete, reads back the full circle, and forwards to the indexer.
//
// The projector implements runtime/messaging.EventPublisher so it slots into the
// circle service's existing domain-event publish path; non-circle / counter-only
// events are ignored.
package searchindex

import (
	"context"
	"fmt"
	"log/slog"
	"strings"

	messaging "quwoquan_service/runtime/messaging"
	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/model"
)

type CircleReader interface {
	LoadForSearch(
		ctx context.Context,
		circleID string,
	) (*model.Circle, bool, error)
}

// Projector applies circle lifecycle events to the unified ES index. It
// implements messaging.EventPublisher so it can be wired as the circle service's
// event publisher (or composed onto an existing one).
//
// Indexing failures are recorded structurally and returned to the dedicated
// outbox relay. The aggregate transaction has already committed, so this keeps
// the relay checkpoint retryable without coupling the primary write to ES.
type Projector struct {
	indexer *es.Indexer
	reader  CircleReader
	logger  *slog.Logger
}

var _ messaging.EventPublisher = (*Projector)(nil)

// Option configures a Projector.
type Option func(*Projector)

// WithLogger sets the structured logger used to record indexing failures.
func WithLogger(logger *slog.Logger) Option {
	return func(p *Projector) {
		if logger != nil {
			p.logger = logger
		}
	}
}

// NewProjector builds a write-time search-index projector.
func NewProjector(
	indexer *es.Indexer,
	reader CircleReader,
	opts ...Option,
) *Projector {
	p := &Projector{
		indexer: indexer,
		reader:  reader,
		logger:  slog.Default(),
	}
	for _, opt := range opts {
		opt(p)
	}
	return p
}

// Publish reconciles a circle lifecycle event into the index. Create/update
// events reconcile the circle against its current eligibility (upsert when
// searchable, delete otherwise); archival removes the doc. Membership / behavior
// / counter-only events do not change the searchable surface and are ignored. It
// returns failures to the dedicated outbox relay so its checkpoint remains
// retryable; the aggregate transaction has already committed.
func (p *Projector) Publish(ctx context.Context, event messaging.DomainEvent) error {
	if p == nil || p.indexer == nil {
		return fmt.Errorf("Circle search projector is not configured")
	}
	circleID := strings.TrimSpace(event.AggregateID)
	if circleID == "" {
		return fmt.Errorf("Circle search event has no aggregate id")
	}
	switch event.Type {
	case "CircleArchived":
		return p.delete(ctx, circleID, event.Type)
	case "CircleCreated", "CircleUpdated":
		return p.reconcile(ctx, circleID, event.Type)
	default:
		// Membership / behavior / counter-only events: nothing searchable changed.
	}
	return nil
}

// reconcile reads the circle back and upserts it when searchable, else removes it
// (e.g. archived, turned private, or vanished). Keeping the index aligned with the
// same eligibility the native source uses avoids a second discoverability truth
// source.
func (p *Projector) reconcile(
	ctx context.Context,
	circleID, eventType string,
) error {
	circle, ok, err := p.reader.LoadForSearch(ctx, circleID)
	if err != nil {
		return fmt.Errorf(
			"load Circle %s for search reconciliation: %w",
			circleID,
			err,
		)
	}
	if !ok || circle == nil {
		return p.delete(ctx, circleID, eventType)
	}
	if !application.CircleSearchEligible(*circle) {
		return p.delete(ctx, circleID, eventType)
	}
	doc := application.ProjectCircleToSearchDocument(*circle)
	if err := p.indexer.Apply(ctx, es.ChangeEvent{Op: es.OpUpsert, Doc: doc}); err != nil {
		p.logger.Warn("search index upsert failed",
			"event", eventType, "circleId", circleID, "err", err)
		return fmt.Errorf("search index upsert Circle %s: %w", circleID, err)
	}
	return nil
}

// delete removes the circle's doc from the index. Replayed deletes are
// idempotent.
func (p *Projector) delete(
	ctx context.Context,
	circleID, eventType string,
) error {
	doc := rtsearch.Document{ObjectType: rtsearch.ObjectTypeCircle, ObjectID: circleID}
	if err := p.indexer.Apply(ctx, es.ChangeEvent{Op: es.OpDelete, Doc: doc}); err != nil {
		p.logger.Warn("search index delete failed",
			"event", eventType, "circleId", circleID, "err", err)
		return fmt.Errorf("search index delete Circle %s: %w", circleID, err)
	}
	return nil
}
