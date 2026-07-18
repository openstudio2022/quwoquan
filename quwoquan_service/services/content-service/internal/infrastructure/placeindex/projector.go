package placeindex

import (
	"context"
	"fmt"
	"log/slog"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/content-service/internal/application/ports"
	"quwoquan_service/services/content-service/internal/application/searchprojection"
	postevent "quwoquan_service/services/content-service/internal/domain/post/event"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

// PostReader reads posts back so a lifecycle event (carrying only an aggregate
// id) can be reconciled against the full post.
type PostReader interface {
	FindByID(ctx context.Context, id string) (*postmodel.Post, bool)
	ListAll(ctx context.Context) ([]postmodel.Post, error)
}

// PlaceProjector keeps the first-party place snapshot store and the unified ES
// index aligned with post lifecycle events. It implements ports.Projector
// so it composes into the in-process projector fan-out alongside the post
// search-index projector.
//
// Like the post search-index projector, indexing/store failures are recorded
// and returned to this projector's dedicated outbox relay. The Post write has
// already committed; the error keeps only the place checkpoint replayable.
type PlaceProjector struct {
	indexer *es.Indexer
	reader  PostReader
	store   PlaceStore
	logger  *slog.Logger
}

// Option configures a PlaceProjector.
type Option func(*PlaceProjector)

// WithLogger sets the structured logger used to record failures.
func WithLogger(logger *slog.Logger) Option {
	return func(p *PlaceProjector) {
		if logger != nil {
			p.logger = logger
		}
	}
}

// NewProjector builds a write-time place-index projector. A nil indexer or store
// makes Project a no-op (ES disabled).
func NewProjector(indexer *es.Indexer, reader PostReader, store PlaceStore, opts ...Option) *PlaceProjector {
	p := &PlaceProjector{indexer: indexer, reader: reader, store: store, logger: slog.Default()}
	for _, opt := range opts {
		opt(p)
	}
	return p
}

// Project reconciles a post lifecycle event into the place snapshot store + ES
// index. Failures must reach the dedicated relay so its checkpoint does not
// acknowledge a partial projection.
func (p *PlaceProjector) Project(ctx context.Context, event ports.ProjectorEvent) error {
	if p == nil || p.indexer == nil || p.store == nil || p.reader == nil {
		return nil
	}
	postID := strings.TrimSpace(event.AggregateID)
	if postID == "" {
		return nil
	}
	switch event.Type {
	case postevent.PostDeleted:
		return p.retractAll(ctx, postID, event.Type)
	case postevent.PostPublished, postevent.PostUpdated, postevent.PostSettingsUpdated, postevent.PostPromotedToWork:
		return p.reconcile(ctx, postID, event.Type)
	default:
		// Counter-only / unrelated events: nothing place-related changed.
	}
	return nil
}

// reconcile reads the post back, materializes the place it references now (when
// eligible), and retracts the post from any other place it used to reference
// (location changed, turned private, or got bound to a canonical entity). The
// single-source rule lives in searchprojection.DerivePlaceRef: a post bound to a
// canonical entity yields no ref, so its old place loses this reference (and is
// deleted once its last free-text reference is gone — carried by entity.homepage).
func (p *PlaceProjector) reconcile(ctx context.Context, postID, eventType string) error {
	currentID := ""
	if post, ok := p.reader.FindByID(ctx, postID); ok && post != nil {
		if ref, eligible := searchprojection.DerivePlaceRef(*post); eligible {
			currentID = ref.PlaceID
			if snap, err := p.store.AddReference(ctx, ref, postID); err != nil {
				p.logger.Warn("place store add reference failed", "event", eventType, "postId", postID, "err", err)
				return fmt.Errorf("place store add reference for %s: %w", postID, err)
			} else {
				if err := p.indexUpsert(ctx, snap, eventType); err != nil {
					return err
				}
			}
		}
	}
	prev, err := p.store.PlacesReferencing(ctx, postID)
	if err != nil {
		p.logger.Warn("place store reverse lookup failed", "event", eventType, "postId", postID, "err", err)
		return fmt.Errorf("place store reverse lookup for %s: %w", postID, err)
	}
	for _, place := range prev {
		if place.PlaceID == currentID {
			continue
		}
		if err := p.retract(ctx, place.PlaceID, postID, eventType); err != nil {
			return err
		}
	}
	return nil
}

// retractAll removes a deleted post from every place it referenced.
func (p *PlaceProjector) retractAll(ctx context.Context, postID, eventType string) error {
	prev, err := p.store.PlacesReferencing(ctx, postID)
	if err != nil {
		p.logger.Warn("place store reverse lookup failed", "event", eventType, "postId", postID, "err", err)
		return fmt.Errorf("place store reverse lookup for %s: %w", postID, err)
	}
	for _, place := range prev {
		if err := p.retract(ctx, place.PlaceID, postID, eventType); err != nil {
			return err
		}
	}
	return nil
}

// retract drops one post's reference from a place, re-indexing the survivor or
// deleting the place doc when no references remain.
func (p *PlaceProjector) retract(ctx context.Context, placeID, postID, eventType string) error {
	snap, remaining, err := p.store.RemoveReference(ctx, placeID, postID)
	if err != nil {
		p.logger.Warn("place store remove reference failed", "event", eventType, "postId", postID, "placeId", placeID, "err", err)
		return fmt.Errorf("place store remove reference %s from %s: %w", postID, placeID, err)
	}
	if remaining <= 0 {
		return p.indexDelete(ctx, placeID, eventType)
	}
	return p.indexUpsert(ctx, snap, eventType)
}

func (p *PlaceProjector) indexUpsert(ctx context.Context, snap searchprojection.PlaceSnapshot, eventType string) error {
	doc := searchprojection.ProjectPlaceToSearchDocument(snap)
	if err := p.indexer.Apply(ctx, es.ChangeEvent{Op: es.OpUpsert, Doc: doc}); err != nil {
		p.logger.Warn("place index upsert failed", "event", eventType, "placeId", snap.PlaceID, "err", err)
		return fmt.Errorf("place index upsert %s: %w", snap.PlaceID, err)
	}
	return nil
}

func (p *PlaceProjector) indexDelete(ctx context.Context, placeID, eventType string) error {
	doc := rtsearch.Document{ObjectType: rtsearch.ObjectTypeLocation, ObjectID: placeID}
	if err := p.indexer.Apply(ctx, es.ChangeEvent{Op: es.OpDelete, Doc: doc}); err != nil {
		p.logger.Warn("place index delete failed", "event", eventType, "placeId", placeID, "err", err)
		return fmt.Errorf("place index delete %s: %w", placeID, err)
	}
	return nil
}
