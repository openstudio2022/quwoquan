package runtimemedia

import "testing"

func TestBuildSlicedObjectKey(t *testing.T) {
	got := BuildSlicedObjectKey(
		"content",
		"image",
		"img-0007",
		"post",
		"fixture_post_001",
		"asset_fixture_post_001",
		"cover",
		"JPG",
	)
	want := "content/image/s/img-0007/post/fixture_post_001/asset_fixture_post_001_cover.jpg"
	if got != want {
		t.Fatalf("unexpected object key: %s", got)
	}
}

func TestExtractSliceIDFromObjectKey(t *testing.T) {
	got := ExtractSliceIDFromObjectKey("content/image/s/img-0007/post/p_1/a_cover.jpg")
	if got != "img-0007" {
		t.Fatalf("unexpected slice id: %s", got)
	}
}

func TestResolveSliceIDFromObjectKeyFallsBackToLegacyPrefixes(t *testing.T) {
	cases := map[string]string{
		"media/avatar/user/u1/v1/avatar.png": LegacyAvatarSliceID,
		"media/background/user/u1/v1/background.png": LegacyAvatarSliceID,
		"media/image/post/p1/v1/cover.png": LegacyImageSliceID,
		"media/video/post/p1/v1/cover.mp4": LegacyVideoSliceID,
	}
	for objectKey, want := range cases {
		if got := ResolveSliceIDFromObjectKey(objectKey); got != want {
			t.Fatalf("unexpected legacy slice for %s: got=%s want=%s", objectKey, got, want)
		}
	}
}
