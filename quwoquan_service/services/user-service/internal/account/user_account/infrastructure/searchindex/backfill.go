package searchindex

import (
	"context"

	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

// defaultBackfillBatchSize bounds how many profiles are pulled (and pushed) per
// page / _bulk round trip.
const defaultBackfillBatchSize = 500

// ProfileLister enumerates profiles for cold-start backfill via keyset
// pagination. The profile store (persistence.PgProfileStore) satisfies it.
type ProfileLister interface {
	ListProfilesForIndex(ctx context.Context, afterUserID string, limit int) ([]model.UserProfile, error)
}

// BulkIndexer is the subset of the ES client backfill needs: ensure the index
// exists, then write batches of change events. *es.Client satisfies it.
type BulkIndexer interface {
	EnsureIndex(ctx context.Context) error
	Bulk(ctx context.Context, index string, events []es.ChangeEvent) error
}

// BackfillReport summarizes a full rebuild for logging / cold-start audit.
type BackfillReport struct {
	TotalProfiles   int `json:"totalProfiles"`
	IndexedProfiles int `json:"indexedProfiles"`
	SkippedProfiles int `json:"skippedProfiles"`
	BatchesPushed   int `json:"batchesPushed"`
}

// Backfill rebuilds the unified index from the live store: it ensures the index
// exists, pages through every profile by ascending user_id, projects the eligible
// (active account + active status) ones through the shared projection, and
// bulk-upserts them per page. It is the cold-start / reconcile entry for the user
// search index. batchSize <= 0 uses the default.
func Backfill(ctx context.Context, indexer BulkIndexer, lister ProfileLister, batchSize int) (BackfillReport, error) {
	var report BackfillReport
	if indexer == nil || lister == nil {
		return report, nil
	}
	if batchSize <= 0 {
		batchSize = defaultBackfillBatchSize
	}
	if err := indexer.EnsureIndex(ctx); err != nil {
		return report, err
	}

	afterUserID := ""
	for {
		page, err := lister.ListProfilesForIndex(ctx, afterUserID, batchSize)
		if err != nil {
			return report, err
		}
		if len(page) == 0 {
			break
		}
		report.TotalProfiles += len(page)
		batch := make([]es.ChangeEvent, 0, len(page))
		for i := range page {
			if !application.UserProfileSearchEligible(page[i]) {
				report.SkippedProfiles++
				continue
			}
			batch = append(batch, es.ChangeEvent{
				Op:  es.OpUpsert,
				Doc: application.ProjectUserProfileToSearchDocument(page[i]),
			})
			report.IndexedProfiles++
		}
		if len(batch) > 0 {
			if err := indexer.Bulk(ctx, "", batch); err != nil {
				return report, err
			}
			report.BatchesPushed++
		}
		// Advance the keyset cursor; a short page means the table is exhausted.
		afterUserID = page[len(page)-1].UserID
		if len(page) < batchSize {
			break
		}
	}
	return report, nil
}
