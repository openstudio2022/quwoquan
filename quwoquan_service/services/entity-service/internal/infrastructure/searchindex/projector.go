// Package searchindex implements the entity domain's write side of the unified
// search index (the entity.search_index_worker module). A write-time projector
// keeps the shared ES/OpenSearch index in sync with homepage lifecycle events,
// and a backfill entry point rebuilds the index from the live store for cold
// start.
//
// It is a pure producer: it never serves queries. The homepage→Document
// projection is owned by application.ProjectHomepageToSearchDocument (single
// source of truth, shared with the native SearchHomepages surface) and the ES
// document shape is owned by runtime/search/es. This package only decides which
// lifecycle events upsert vs delete and forwards to the indexer. Unlike the
// content domain, entity-service has no Mongo change-stream / outbox bus, so the
// homepage service emits the full post-mutation snapshot inside the event and the
// projector never reads state back.
package searchindex

import (
	"context"
	"log/slog"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/entity-service/internal/application"
)

// Projector applies homepage lifecycle events to the unified ES index. It
// implements application.Projector so the homepage service can call it directly
// after a mutation that changes the searchable surface.
//
// Indexing failures are recorded structurally (logged with event/homepage
// context) but never propagate: the search index is a derived read store, so a
// transient ES outage must not block or fail the primary homepage write path.
type Projector struct {
	indexer *es.Indexer
	logger  *slog.Logger
}

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
func NewProjector(indexer *es.Indexer, opts ...Option) *Projector {
	p := &Projector{
		indexer: indexer,
		logger:  slog.Default(),
	}
	for _, opt := range opts {
		opt(p)
	}
	return p
}

// Project reconciles a homepage lifecycle event into the index. Upsert events
// reconcile the carried snapshot against its current eligibility (upsert when
// published, delete otherwise); remove events delete the doc. It always returns
// nil so a failing index write cannot break the homepage write path.
func (p *Projector) Project(ctx context.Context, event application.ProjectorEvent) error {
	if p == nil || p.indexer == nil {
		return nil
	}
	homepageID := strings.TrimSpace(event.HomepageID)
	if homepageID == "" {
		return nil
	}
	switch event.Type {
	case application.ProjectorEventHomepageRemoved:
		p.delete(ctx, homepageID, event.Type)
	case application.ProjectorEventHomepageUpserted:
		p.reconcile(ctx, homepageID, event)
	default:
		// Unrelated events: nothing searchable changed.
	}
	return nil
}

// reconcile upserts the carried homepage snapshot when it is searchable, else
// removes it (e.g. taken offline, or the snapshot is absent). Aligning the index
// with the same eligibility SearchHomepages uses avoids a second discoverability
// truth source.
func (p *Projector) reconcile(ctx context.Context, homepageID string, event application.ProjectorEvent) {
	if event.Homepage == nil || !application.HomepageSearchEligible(*event.Homepage) {
		p.delete(ctx, homepageID, event.Type)
		return
	}
	doc := application.ProjectHomepageToSearchDocument(*event.Homepage)
	if err := p.indexer.Apply(ctx, es.ChangeEvent{Op: es.OpUpsert, Doc: doc}); err != nil {
		p.logger.Warn("search index upsert failed",
			"event", event.Type, "homepageId", homepageID, "err", err)
	}
}

// delete removes the homepage's doc from the index. Replayed deletes are
// idempotent.
func (p *Projector) delete(ctx context.Context, homepageID, eventType string) {
	doc := rtsearch.Document{ObjectType: rtsearch.ObjectTypeEntityHomepage, ObjectID: homepageID}
	if err := p.indexer.Apply(ctx, es.ChangeEvent{Op: es.OpDelete, Doc: doc}); err != nil {
		p.logger.Warn("search index delete failed",
			"event", eventType, "homepageId", homepageID, "err", err)
	}
}
