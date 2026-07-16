// Package searchindex implements the content domain's write side of the unified
// search index (the content.search_index_worker module). A write-time projector
// keeps the shared ES/OpenSearch index in sync with post lifecycle events, and a
// backfill entry point rebuilds the index from the live store for cold start.
//
// It is a pure producer: it never serves queries. The post→Document projection is
// owned by searchprojection.ProjectPostToSearchDocument (single source of truth, shared
// with the native retrieve candidate source) and the ES document shape is owned by
// runtime/search/es. This package only decides which lifecycle events upsert vs
// delete, reads back the full post, and forwards to the indexer.
package searchindex

import (
	"context"
	"fmt"
	"log/slog"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/content-service/internal/application/ports"
	"quwoquan_service/services/content-service/internal/application/searchprojection"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

// PostReader reads posts back so a lifecycle event (which carries only an
// aggregate id + a thin payload) can be reconciled against the full post.
type PostReader interface {
	FindByID(ctx context.Context, id string) (*postmodel.Post, bool)
	ListAll(ctx context.Context) ([]postmodel.Post, error)
}

// Projector applies post lifecycle events to the unified ES index. It implements
// ports.Projector so it can be composed into the in-process projector
// fan-out alongside the discovery/recommend projectors.
//
// Indexing failures are recorded structurally and returned to the dedicated
// outbox consumer. The aggregate transaction has already committed, so an ES
// outage never fails the primary write; returning the error prevents that
// consumer checkpoint from advancing and preserves replay.
type Projector struct {
	indexer *es.Indexer
	reader  PostReader
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
func NewProjector(indexer *es.Indexer, reader PostReader, opts ...Option) *Projector {
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

// Project reconciles a post lifecycle event into the index. Content/visibility
// changing events reconcile the post against its current eligibility (upsert when
// searchable, delete otherwise); deletions remove the doc. Counter-only events
// (reactions, behavior batches) do not change the searchable surface and are
// ignored. Each projector owns an independent outbox checkpoint, so a failing
// index write must propagate to its relay rather than being acknowledged.
func (p *Projector) Project(ctx context.Context, event ports.ProjectorEvent) error {
	if p == nil || p.indexer == nil {
		return nil
	}
	postID := strings.TrimSpace(event.AggregateID)
	if postID == "" {
		return nil
	}
	switch event.Type {
	case "PostDeleted":
		return p.delete(ctx, postID, event.Type)
	case "PostCreated", "PostPublished", "PostUpdated", "PostSettingsUpdated", "PostPromotedToWork":
		return p.reconcile(ctx, postID, event.Type)
	default:
		// Counter-only / unrelated events: nothing searchable changed.
	}
	return nil
}

// reconcile reads the post back and upserts it when searchable, else removes it
// (e.g. unpublished, turned private, or vanished). Keeping the index aligned with
// the same eligibility the native source uses avoids a second discoverability
// truth source.
func (p *Projector) reconcile(ctx context.Context, postID, eventType string) error {
	post, ok := p.reader.FindByID(ctx, postID)
	if !ok || post == nil {
		// Post is gone from the store: ensure it is not left in the index.
		return p.delete(ctx, postID, eventType)
	}
	if !searchEligible(post) {
		return p.delete(ctx, postID, eventType)
	}
	doc := searchprojection.ProjectPostToSearchDocument(*post)
	if err := p.indexer.Apply(ctx, es.ChangeEvent{Op: es.OpUpsert, Doc: doc}); err != nil {
		p.logger.Warn("search index upsert failed",
			"event", eventType, "postId", postID, "err", err)
		return fmt.Errorf("search index upsert %s: %w", postID, err)
	}
	return nil
}

// delete removes the post's doc from the index. Replayed deletes are idempotent.
func (p *Projector) delete(ctx context.Context, postID, eventType string) error {
	doc := rtsearch.Document{ObjectType: rtsearch.ObjectTypeContentPost, ObjectID: postID}
	if err := p.indexer.Apply(ctx, es.ChangeEvent{Op: es.OpDelete, Doc: doc}); err != nil {
		p.logger.Warn("search index delete failed",
			"event", eventType, "postId", postID, "err", err)
		return fmt.Errorf("search index delete %s: %w", postID, err)
	}
	return nil
}

// searchEligible mirrors the store's ListPublished filter (published + public):
// only those posts are reachable through the native candidate source, so the ES
// index must contain exactly the same set.
func searchEligible(post *postmodel.Post) bool {
	if !strings.EqualFold(strings.TrimSpace(post.Status), "published") {
		return false
	}
	return strings.EqualFold(strings.TrimSpace(post.Visibility), "public")
}
