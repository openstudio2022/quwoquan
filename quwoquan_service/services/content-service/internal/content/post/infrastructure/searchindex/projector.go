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
	postevent "quwoquan_service/services/content-service/generated/content/post/contract/event"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
	"quwoquan_service/services/content-service/internal/content/post/application/searchprojection"
)

// PostReader reads posts back so a lifecycle event (which carries only an
// aggregate id + a thin payload) can be reconciled against the full post.
// Load 必须保留 found 与 error；把 Mongo/解码错误折叠成 not-found 会错误删除
// 搜索文档并推进该 consumer checkpoint。
type PostReader interface {
	Load(ctx context.Context, id string) (*postmodel.Post, bool, error)
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
// changing events (including deletion, which keeps the Post row with
// status=deleted) reconcile the post against its current eligibility: upsert
// when searchable, versioned tombstone otherwise. Counter-only events
// (reactions, behavior batches) do not change the searchable surface and are
// ignored. Each projector owns an independent outbox checkpoint, so a failing
// index write must propagate to its relay rather than being acknowledged.
func (p *Projector) Project(ctx context.Context, event ports.ProjectorEvent) error {
	if p == nil || p.indexer == nil {
		return fmt.Errorf("Post search projector is not configured")
	}
	postID := strings.TrimSpace(event.AggregateID)
	if postID == "" {
		return fmt.Errorf("Post search event has no aggregate id")
	}
	switch event.Type {
	case postevent.PostDeleted, postevent.PostPublished, postevent.PostUpdated,
		postevent.PostSettingsUpdated, postevent.PostPromotedToWork:
		return p.reconcile(ctx, postID, event)
	default:
		// Counter-only / unrelated events: nothing searchable changed.
	}
	return nil
}

// reconcile reads the post back and upserts it when searchable, else writes a
// versioned tombstone (e.g. deleted, unpublished, turned private, or vanished).
// Keeping the index aligned with the same eligibility the native source uses
// avoids a second discoverability truth source.
//
// sourceVersion 来源（DEC-002）：读到 Post 时用其权威 version（server-owned
// CAS 单调递增）；Post 已不可读（硬删除）时用触发本次投影的 outbox 事实的
// AggregateVersion —— 它是该 Post 最后一次已提交的版本，任何更高版本的写入
// 都会由 Elasticsearch 外部版本比较拒绝本 tombstone，而不是被它覆盖。
func (p *Projector) reconcile(ctx context.Context, postID string, event ports.ProjectorEvent) error {
	post, ok, err := p.reader.Load(ctx, postID)
	if err != nil {
		return fmt.Errorf("load post %s for search reconciliation: %w", postID, err)
	}
	if !ok || post == nil {
		if event.AggregateVersion <= 0 {
			return fmt.Errorf(
				"Post %s is unreadable and event %s carries no aggregate version for its search tombstone",
				postID, event.Type,
			)
		}
		return p.tombstone(ctx, postID, event.Type, event.AggregateVersion)
	}
	if post.Version <= 0 {
		return fmt.Errorf("Post %s has no positive version for search projection", postID)
	}
	if !searchEligible(post) {
		return p.tombstone(ctx, postID, event.Type, post.Version)
	}
	doc := searchprojection.ProjectPostToSearchDocument(*post)
	if _, err := p.indexer.ApplyVersioned(ctx, es.VersionedChangeEvent{
		Op: es.OpUpsert, Doc: doc, SourceVersion: post.Version,
	}); err != nil {
		p.logger.Warn("search index upsert failed",
			"event", event.Type, "postId", postID, "err", err)
		return fmt.Errorf("search index upsert %s: %w", postID, err)
	}
	return nil
}

// tombstone writes the post's versioned soft-delete document. Replayed and
// stale tombstones are rejected atomically by the provider, never resurrected.
func (p *Projector) tombstone(ctx context.Context, postID, eventType string, sourceVersion int64) error {
	doc := rtsearch.Document{ObjectType: rtsearch.ObjectTypeContentPost, ObjectID: postID}
	if _, err := p.indexer.ApplyVersioned(ctx, es.VersionedChangeEvent{
		Op: es.OpDelete, Doc: doc, SourceVersion: sourceVersion,
	}); err != nil {
		p.logger.Warn("search index tombstone failed",
			"event", eventType, "postId", postID, "err", err)
		return fmt.Errorf("search index tombstone %s: %w", postID, err)
	}
	return nil
}

// searchEligible mirrors the store's ListPublished filter
// (published + public + moderation approved): only those posts are reachable
// through the native candidate source, so the ES index must contain the same set.
func searchEligible(post *postmodel.Post) bool {
	if !strings.EqualFold(strings.TrimSpace(post.Status), "published") {
		return false
	}
	return strings.EqualFold(strings.TrimSpace(post.Visibility), "public") &&
		strings.EqualFold(strings.TrimSpace(post.ModerationStatus), "approved")
}
