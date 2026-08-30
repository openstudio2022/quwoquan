package releaseimport_test

import (
	"testing"

	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func TestRuntimePostIDUsesOnlyStableContentID(t *testing.T) {
	contentID := "qwq_data_stable_content_001"
	first := RuntimePostID(contentID)
	next := RuntimePostID(contentID)
	if first == "" || first != next {
		t.Fatalf("stable contentId must own runtime identity: first=%q next=%q", first, next)
	}
}

func TestRuntimePostIDRejectsMissingContentID(t *testing.T) {
	if got := RuntimePostID(""); got != "" {
		t.Fatalf("missing contentId must not derive a runtime identity: %q", got)
	}
}
