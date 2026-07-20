// Package searchindex implements the user domain's write side of the unified
// search index (the user.search_index_worker module). A write-time projector
// keeps the shared ES/OpenSearch index in sync with profile lifecycle events, and
// a backfill entry point rebuilds the index from the live store for cold start.
//
// It is a pure producer: it never serves queries. The profile→Document projection
// is owned by application.ProjectUserProfileToSearchDocument (single source of
// truth) and the ES document shape is owned by runtime/search/es. This package
// only decides which lifecycle events upsert vs delete, reads back the full
// profile, and forwards to the indexer.
//
// The projector implements application.UserEventPublisher so it composes onto the
// user service's existing event publisher; non-profile events are ignored.
package searchindex

import (
	"context"
	"fmt"
	"log/slog"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/user-service/internal/application"
	event "quwoquan_service/services/user-service/internal/domain/user/event"
	"quwoquan_service/services/user-service/internal/domain/user/model"
)

// ProfileReader reads a profile back so a lifecycle event (which carries only ids
// + a thin payload) can be reconciled against the full profile. The profile store
// (persistence.PgProfileStore) satisfies it.
type ProfileReader interface {
	FindByID(ctx context.Context, userID string) (*model.UserProfile, error)
}

// Projector applies profile lifecycle events to the unified ES index. It
// implements application.UserEventPublisher so it can be composed onto the user
// service's event publisher fan-out.
//
// Indexing failures are recorded structurally (logged with event/user context)
// but never propagate: the search index is a derived read store, so a transient
// ES outage must not block or fail the primary profile write path.
type Projector struct {
	indexer *es.Indexer
	reader  ProfileReader
	logger  *slog.Logger
}

var _ application.UserEventPublisher = (*Projector)(nil)

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
func NewProjector(indexer *es.Indexer, reader ProfileReader, opts ...Option) *Projector {
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

// PublishUserEvent reconciles a profile lifecycle event into the index. Profile /
// avatar / registration events reconcile the profile against its current
// eligibility (upsert when discoverable, delete otherwise). Relationship / block /
// counter events do not change the searchable surface and are ignored. 普通资料
// 更新保持 best-effort；UserAccountClosed 删除失败必须返回，使 durable outbox 重试。
func (p *Projector) PublishUserEvent(ctx context.Context, eventType, userID, _ string, _ map[string]any) error {
	if p == nil || p.indexer == nil {
		return nil
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return nil
	}
	switch eventType {
	case event.UserAccountClosed:
		// UserAccountClosed reconciles to a delete: a closed account is no
		// longer search eligible, so the read-back drops it from the index.
		return p.reconcile(ctx, userID, eventType)
	case event.UserProfileUpdated, event.UserAvatarUpdated, event.UserRegistered:
		if err := p.reconcile(ctx, userID, eventType); err != nil {
			p.logger.Warn(
				"search index reconcile failed",
				"event",
				eventType,
				"userId",
				userID,
				"err",
				err,
			)
		}
	default:
		// Non-profile / counter-only events: nothing searchable changed.
	}
	return nil
}

// reconcile reads the profile back and upserts it when discoverable, else removes
// it (e.g. suspended, deleted, or vanished). Keeping the index aligned with the
// same eligibility the discoverable set uses avoids a second discoverability truth
// source.
func (p *Projector) reconcile(
	ctx context.Context,
	userID, eventType string,
) error {
	profile, err := p.reader.FindByID(ctx, userID)
	if err != nil {
		return fmt.Errorf("search index read-back: %w", err)
	}
	if profile == nil || !application.UserProfileSearchEligible(*profile) {
		return p.delete(ctx, userID)
	}
	doc := application.ProjectUserProfileToSearchDocument(*profile)
	if err := p.indexer.Apply(ctx, es.ChangeEvent{Op: es.OpUpsert, Doc: doc}); err != nil {
		return fmt.Errorf("search index upsert: %w", err)
	}
	return nil
}

// delete removes the profile's doc from the index. Replayed deletes are
// idempotent.
func (p *Projector) delete(ctx context.Context, userID string) error {
	doc := rtsearch.Document{ObjectType: rtsearch.ObjectTypeUserProfile, ObjectID: userID}
	if err := p.indexer.Apply(ctx, es.ChangeEvent{Op: es.OpDelete, Doc: doc}); err != nil {
		return fmt.Errorf("search index delete: %w", err)
	}
	return nil
}
