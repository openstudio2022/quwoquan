// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-008
// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
package model_test

import (
	"testing"

	moderationmodel "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/domain/model"
)

func TestNilPostModerationCaseIdentityAccessorsReturnZeroValues(t *testing.T) {
	t.Parallel()

	var caseItem *moderationmodel.PostModerationCase
	if caseItem.ID() != "" ||
		caseItem.Version() != 0 ||
		caseItem.PostID() != "" ||
		caseItem.PostVersion() != 0 ||
		caseItem.ContentDigest() != "" ||
		caseItem.Status() != "" ||
		caseItem.ReviewerID() != "" ||
		caseItem.Snapshot() != (moderationmodel.Snapshot{}) {
		t.Fatal("nil moderation case identity accessors must return zero values")
	}
}
