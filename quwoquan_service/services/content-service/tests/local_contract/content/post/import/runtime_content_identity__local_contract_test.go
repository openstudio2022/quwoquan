package releaseimport_test

import (
	"testing"

	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func TestRuntimePostIDPrefersStableContentIDAcrossVersions(t *testing.T) {
	contentID := "qwq_data_stable_content_001"
	firstRef := "posts/article/攻略/测试景区攻略/3"
	nextRef := "posts/article/攻略/测试景区攻略/4"

	first := RuntimePostID(contentID, firstRef)
	next := RuntimePostID(contentID, nextRef)
	if first == "" || first != next {
		t.Fatalf("stable contentId must own runtime identity: first=%q next=%q", first, next)
	}
	if first == LegacyRuntimePostID(firstRef) {
		t.Fatalf("content identity must not remain bound to legacy postRef: %q", first)
	}
}

func TestRuntimePostIDKeepsExplicitLegacyFallbackForMigration(t *testing.T) {
	postRef := "posts/article/攻略/测试景区攻略/3"
	if got, want := RuntimePostID("", postRef), LegacyRuntimePostID(postRef); got != want {
		t.Fatalf("empty legacy contentId fallback drift: got=%q want=%q", got, want)
	}
}
