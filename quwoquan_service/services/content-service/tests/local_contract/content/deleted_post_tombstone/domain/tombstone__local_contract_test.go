// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/spec.md#sit-002
package domain_test

import (
	"testing"
	"time"

	tombstonemodel "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/domain/model"
)

func TestDeletedPostTombstoneRequiresBoundedImmutableLifecycle(t *testing.T) {
	deletedAt := time.Date(2026, 8, 2, 9, 0, 0, 0, time.UTC)
	valid := tombstonemodel.Tombstone{
		PostID:    "post-deleted",
		AuthorID:  "author-deleted",
		Reason:    "author_delete",
		DeletedAt: deletedAt,
		ExpireAt:  deletedAt.Add(30 * 24 * time.Hour),
	}
	if err := valid.Validate(); err != nil {
		t.Fatalf("valid DeletedPostTombstone rejected: %v", err)
	}
	invalid := valid
	invalid.ExpireAt = invalid.DeletedAt
	if err := invalid.Validate(); err == nil {
		t.Fatal("non-forward tombstone expiry must be rejected")
	}
}
