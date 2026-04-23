package runtimemedia

import "testing"

func TestBuildAvatarGroupAssetRef(t *testing.T) {
	ref := BuildAvatarGroupAssetRef(
		"conversation_001",
		"ga_conversation_001_v1",
		1,
		"abcdef1234567890",
		"cdn.example.com",
	)

	if ref.AssetKind != AssetKindAvatarGroup {
		t.Fatalf("expected avatar group kind, got %s", ref.AssetKind)
	}
	if ref.ObjectKey == "" {
		t.Fatal("expected object key")
	}
	if ref.URL != "https://cdn.example.com/media/avatar/conversation/conversation_001/v1/abcdef1234567890.png?v=1" {
		t.Fatalf("unexpected url: %s", ref.URL)
	}
}

func TestBuildAssetURLFallsBackToDefaultDomain(t *testing.T) {
	url := BuildAssetURL("", "media/avatar/conversation/c_1/v2/hash.png", 2)
	if url != "https://mock-cdn.example.com/media/avatar/conversation/c_1/v2/hash.png?v=2" {
		t.Fatalf("unexpected fallback url: %s", url)
	}
}
