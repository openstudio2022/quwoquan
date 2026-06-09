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

func TestResolveSliceIDFromObjectKeyRequiresExplicitSlice(t *testing.T) {
	got := ResolveSliceIDFromObjectKey("content/avatar/s/archived-avatar/user/u1/avatar/avatar.png")
	if got != ArchivedAvatarSliceID {
		t.Fatalf("unexpected archived slice id: %s", got)
	}
	if got := ResolveSliceIDFromObjectKey("media/avatar/no-slice/user/u1/v1/avatar.png"); got != "" {
		t.Fatalf("expected path without slice to stop resolving, got %s", got)
	}
}
