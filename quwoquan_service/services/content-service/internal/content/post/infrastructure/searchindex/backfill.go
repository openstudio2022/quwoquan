package searchindex

import (
	"context"
	"fmt"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/content-service/internal/content/post/application/searchprojection"
)

// VersionedIndexer is the only write surface backfill may use: every document
// is written under the Post's own sourceVersion so a rebuild can never regress
// a newer write-time projection (DEC-002). *es.Indexer satisfies it.
type VersionedIndexer interface {
	ApplyVersioned(ctx context.Context, event es.VersionedChangeEvent) (bool, error)
}

// BackfillReport summarizes a full rebuild for logging / cold-start audit.
type BackfillReport struct {
	TotalPosts      int `json:"totalPosts"`
	IndexedPosts    int `json:"indexedPosts"`
	TombstonedPosts int `json:"tombstonedPosts"`
	// StaleWrites counts documents the provider rejected as not newer than the
	// version it already holds (an idempotent replay or a concurrent write-time
	// projection that already advanced further). They are not failures.
	StaleWrites int `json:"staleWrites"`
}

// Backfill reconciles the unified index from the live store: it lists every
// post, projects the eligible (published + public + approved) ones through the
// shared projection and upserts them under their authoritative version, and
// writes versioned tombstones for the rest. Index existence is the assembly's
// responsibility (Built.EnsureIndex) so backfill and write-time projection share
// one bootstrap path.
func Backfill(ctx context.Context, indexer VersionedIndexer, reader PostReader) (BackfillReport, error) {
	var report BackfillReport
	if indexer == nil || reader == nil {
		return report, fmt.Errorf(
			"Post search backfill requires indexer and reader",
		)
	}
	posts, err := reader.ListAll(ctx)
	if err != nil {
		return report, fmt.Errorf("list posts: %w", err)
	}
	report.TotalPosts = len(posts)
	for i := range posts {
		post := &posts[i]
		if post.Version <= 0 {
			return report, fmt.Errorf("Post %s has no positive version for search backfill", post.ID)
		}
		event := es.VersionedChangeEvent{SourceVersion: post.Version}
		if searchEligible(post) {
			event.Op = es.OpUpsert
			event.Doc = searchprojection.ProjectPostToSearchDocument(*post)
			report.IndexedPosts++
		} else {
			event.Op = es.OpDelete
			event.Doc = rtsearch.Document{
				ObjectType: rtsearch.ObjectTypeContentPost,
				ObjectID:   post.ID,
			}
			report.TombstonedPosts++
		}
		applied, err := indexer.ApplyVersioned(ctx, event)
		if err != nil {
			return report, fmt.Errorf("search backfill %s %s: %w", event.Op, post.ID, err)
		}
		if !applied {
			report.StaleWrites++
		}
	}
	return report, nil
}
