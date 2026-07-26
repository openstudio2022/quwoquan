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
	"log/slog"
	"strings"

	messaging "quwoquan_service/runtime/messaging"
	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
)

// Projector applies circle lifecycle events to the unified ES index. It
// implements messaging.EventPublisher so it can be wired as the circle service's
// event publisher (or composed onto an existing one).
//
// Indexing failures are recorded structurally (logged with event/circle context)
// but never propagate: the search index is a derived read store, so a transient
// ES outage must not block or fail the primary circle write path.
type Projector struct {
	indexer *es.Indexer
	reader  application.CircleReader
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
func NewProjector(indexer *es.Indexer, reader application.CircleReader, opts ...Option) *Projector {
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
// always returns nil so a failing index write cannot break the publish path or
// the primary circle write path.
func (p *Projector) Publish(ctx context.Context, event messaging.DomainEvent) error {
	if p == nil || p.indexer == nil {
		return nil
	}
	circleID := strings.TrimSpace(event.AggregateID)
	if circleID == "" {
		return nil
	}
	switch event.Type {
	case "CircleArchived":
		p.delete(ctx, circleID, event.Type)
	case "CircleCreated", "CircleUpdated":
		p.reconcile(ctx, circleID, event.Type)
	default:
		// Membership / behavior / counter-only events: nothing searchable changed.
	}
	return nil
}

// reconcile reads the circle back and upserts it when searchable, else removes it
// (e.g. archived, turned private, or vanished). Keeping the index aligned with the
// same eligibility the native source uses avoids a second discoverability truth
// source.
func (p *Projector) reconcile(ctx context.Context, circleID, eventType string) {
	circle, ok := p.reader.FindByID(ctx, circleID)
	if !ok || circle == nil {
		p.delete(ctx, circleID, eventType)
		return
	}
	if !application.CircleSearchEligible(*circle) {
		p.delete(ctx, circleID, eventType)
		return
	}
	doc := application.ProjectCircleToSearchDocument(*circle)
	if err := p.indexer.Apply(ctx, es.ChangeEvent{Op: es.OpUpsert, Doc: doc}); err != nil {
		p.logger.Warn("search index upsert failed",
			"event", eventType, "circleId", circleID, "err", err)
	}
}

// delete removes the circle's doc from the index. Replayed deletes are
// idempotent.
func (p *Projector) delete(ctx context.Context, circleID, eventType string) {
	doc := rtsearch.Document{ObjectType: rtsearch.ObjectTypeCircle, ObjectID: circleID}
	if err := p.indexer.Apply(ctx, es.ChangeEvent{Op: es.OpDelete, Doc: doc}); err != nil {
		p.logger.Warn("search index delete failed",
			"event", eventType, "circleId", circleID, "err", err)
	}
}
