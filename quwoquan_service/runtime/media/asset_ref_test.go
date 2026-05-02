package runtimemedia

import "testing"

func TestBuildAvatarGroupAssetRef(t *testing.T) {
	ref := BuildAvatarGroupAssetRef(
		"conversation_001",
		"ga_conversation_001_v1",
		1,
		"abcdef1234567890",
		"https://cdn.example.com",
	)

	if ref.AssetKind != AssetKindAvatarGroup {
		t.Fatalf("expected avatar group kind, got %s", ref.AssetKind)
	}
	if ref.ObjectKey == "" {
		t.Fatal("expected object key")
	}
	want := "https://cdn.example.com/media/avatar/conversation/conversation_001/v1/abcdef1234567890.png?v=1"
	if ref.URL != want {
		t.Fatalf("unexpected url: %s", ref.URL)
	}
}

func TestBuildAssetURLEmptyBaseReturnsEmpty(t *testing.T) {
	url := BuildAssetURL("", "media/avatar/conversation/c_1/v2/hash.png", 2)
	if url != "" {
		t.Fatalf("expected empty url, got %s", url)
	}
}

func TestNormalizeMediaCDNBaseKeepsExplicitBase(t *testing.T) {
	if got := NormalizeMediaCDNBase("https://cdn.example.com/"); got != "https://cdn.example.com" {
		t.Fatalf("unexpected %q", got)
	}
	if got := BuildPublicMediaURL("cdn.example.com", "media/avatar/a.png", 1); got != "" {
		t.Fatalf("unexpected %q", got)
	}
}
