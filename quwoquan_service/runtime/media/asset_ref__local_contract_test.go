// spec_ref: specs/feature-tree/runtime/runtime-media/media-upload-and-storage/spec.md#gwt-002

package runtimemedia

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestBuildAvatarGroupDeliveryReferenceUsesOnePublicSliceIdentity(t *testing.T) {
	ref := BuildAvatarGroupDeliveryReference(
		"conversation_001",
		"ga_conversation_001",
		1,
		"abcdef1234567890",
		"https://cdn.example.com",
	)

	if ref.AssetKind != AssetKindAvatarGroup {
		t.Fatalf("expected avatar group kind, got %s", ref.AssetKind)
	}
	if ref.PublicSliceKey == "" {
		t.Fatal("expected public slice key")
	}
	want := "https://cdn.example.com/media/avatar/s/conversation/conversation_001/v1/abcdef1234567890.png"
	if ref.DeliveryURI != want {
		t.Fatalf("unexpected delivery URI: %s", ref.DeliveryURI)
	}
	if ref.PublicSliceKey != "media/avatar/s/conversation/conversation_001/v1/abcdef1234567890.png" {
		t.Fatalf("unexpected public slice key: %s", ref.PublicSliceKey)
	}
}

func TestGroupAvatarDeliveryReferenceDoesNotSerializeObjectKey(t *testing.T) {
	ref := BuildAvatarGroupDeliveryReference(
		"conversation_001",
		"ga_conversation_001",
		1,
		"abcdef1234567890",
		"https://cdn.example.com",
	)
	encoded, err := json.Marshal(ref)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if strings.Contains(string(encoded), "objectKey") {
		t.Fatalf("delivery reference leaked a second storage identity: %s", encoded)
	}
}

func TestBuildPublicMediaURLEmptyOrInvalidBaseReturnsEmpty(t *testing.T) {
	if got := BuildPublicMediaURL("", "media/avatar/s/conversation/c_1/v2/hash.png", 2); got != "" {
		t.Fatalf("expected empty URL, got %s", got)
	}
	if got := BuildPublicMediaURL("cdn.example.com", "media/avatar/s/conversation/c_1/v2/hash.png", 2); got != "" {
		t.Fatalf("expected empty URL for bare host, got %s", got)
	}
}

func TestNormalizeMediaCDNBaseRequiresHTTPS(t *testing.T) {
	if got := NormalizeMediaCDNBase("https://cdn.example.com/"); got != "https://cdn.example.com" {
		t.Fatalf("unexpected %q", got)
	}
	if got := NormalizeMediaCDNBase("http://cdn.example.com"); got != "" {
		t.Fatalf("expected non-HTTPS base rejection, got %q", got)
	}
	if got := NormalizeMediaCDNBase("https://cdn.example.com/media/image"); got != "https://cdn.example.com/media/image" {
		t.Fatalf("expected canonical role path base, got %q", got)
	}
	if got := BuildPublicMediaURL("https://cdn.example.com", "media/avatar/a.png", 1); got != "" {
		t.Fatalf("unexpected non-canonical key URL %q", got)
	}
}

func TestResolveReleaseMediaAssetUsesSameHTTPSBaseValidationAsURLBuilder(t *testing.T) {
	const ownerRef = "entities/地点/景区/九寨沟"
	const assetID = "asset_fixture_001"
	const digest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	publicSliceKey := BuildContentMediaPublicSliceKey("image", assetID, 1, "image/jpeg")
	assets := map[string]ReleaseMediaAsset{
		assetID: {
			AssetID:            assetID,
			Kind:               "image",
			Version:            1,
			ContentType:        "image/jpeg",
			PublicSliceKey:     publicSliceKey,
			SHA256:             digest,
			OwnerRefs:          []string{ownerRef},
			RightsSnapshotRefs: []string{"objects/" + ownerRef + "/rights_snapshots/r1.json"},
		},
	}

	if _, err := ResolveReleaseMediaAsset(
		assets,
		MediaDeliveryBases{Image: "http://media.example.com"},
		assetID,
		"image",
		digest,
		ownerRef,
	); err == nil {
		t.Fatal("expected non-HTTPS media base to be rejected before returning a resolution")
	}

	resolved, err := ResolveReleaseMediaAsset(
		assets,
		MediaDeliveryBases{Image: "https://media.example.com"},
		assetID,
		"image",
		digest,
		ownerRef,
	)
	if err != nil {
		t.Fatalf("resolve HTTPS delivery: %v", err)
	}
	want := "https://media.example.com/" + publicSliceKey
	if resolved.PublicURL != want {
		t.Fatalf("unexpected public URL: got %q want %q", resolved.PublicURL, want)
	}

	resolved, err = ResolveReleaseMediaAsset(
		assets,
		MediaDeliveryBases{Image: "https://media.example.com/media/image"},
		assetID,
		"image",
		digest,
		ownerRef,
	)
	if err != nil {
		t.Fatalf("resolve canonical role path base: %v", err)
	}
	if resolved.PublicURL != want {
		t.Fatalf("role base must preserve one canonical media path: got %q want %q", resolved.PublicURL, want)
	}
	if got := BuildPublicMediaURL(
		"https://media.example.com/media/video",
		publicSliceKey,
		1,
	); got != "" {
		t.Fatalf("cross-kind role base must fail closed, got %q", got)
	}
}

func TestBuildPublicMediaURLRejectsCASObjectKey(t *testing.T) {
	casKeys := []string{
		"media/objects/sha256/aa/bb/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg",
		"media/objects/sha256/0a/a5/0aa58a9a6d6061e8f28f86b88662a053bd3803e1215bc73325e8be6fce655d1d.png",
		"/media/objects/sha256/cc/dd/cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc.mp4",
	}
	for _, key := range casKeys {
		if got := BuildPublicMediaURL("https://cdn.example.com", key, 1); got != "" {
			t.Fatalf("expected CAS object key rejection for %q, got %q", key, got)
		}
	}
	if got := BuildPublicMediaURL(
		"https://cdn.example.com",
		"media/image/s/archived-image/post/fixture_photo_001/v1/cover.png",
		1,
	); got != "https://cdn.example.com/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" {
		t.Fatalf("unexpected valid public slice URL %q", got)
	}
	if got := BuildPublicMediaURL(
		"https://cdn.example.com",
		"media/image/s/archived-image/post/fixture_photo_001/v1/cover.png",
		0,
	); got != "" {
		t.Fatalf("zero version must fail closed instead of bypassing path validation, got %q", got)
	}
	if got := BuildPublicMediaURL(
		"https://cdn.example.com",
		"media/image/s/archived-image/post/fixture_photo_001/v1/cover.png",
		-1,
	); got != "" {
		t.Fatalf("negative version must fail closed instead of falling back to v1, got %q", got)
	}
	if got := BuildPublicMediaURL(
		"https://cdn.example.com",
		"media/image/s/archived-image/post/fixture_photo_001/v1/cover.png",
		2,
	); got != "" {
		t.Fatalf("mismatched path/request version must fail closed, got %q", got)
	}
	if got := BuildPublicMediaURL(
		"https://cdn.example.com",
		"media/attachment/s/asset/attachment_001/v1/source.pdf",
		1,
	); got != "https://cdn.example.com/media/attachment/s/asset/attachment_001/v1/source.pdf" {
		t.Fatalf("unexpected attachment public slice URL %q", got)
	}
	if got := BuildPublicMediaURL(
		"https://cdn.example.com",
		"media/video/s/asset/video_001/source.mp4",
		1,
	); got != "" {
		t.Fatalf("unversioned public slice must fail closed, got %q", got)
	}
}

func TestPublicSliceBuildersRejectInvalidVersionInsteadOfFallingBackToV1(t *testing.T) {
	if got := BuildAvatarPublicSliceKey("user", "user_001", 0, "digest"); got != "" {
		t.Fatalf("avatar key builder must reject zero version, got %q", got)
	}
	if got := BuildContentMediaPublicSliceKey("image", "asset_001", -1, "image/png"); got != "" {
		t.Fatalf("content key builder must reject negative version, got %q", got)
	}
	if version, ok := PublicSliceVersion(
		"media/image/s/asset/asset_001/v3/source.png",
	); !ok || version != 3 {
		t.Fatalf("expected canonical path version 3, got version=%d ok=%v", version, ok)
	}
	if _, ok := PublicSliceVersion("media/image/s/asset/asset_001/source.png"); ok {
		t.Fatal("unversioned public slice must not expose a version")
	}
}

func TestBuildContentMediaPublicSliceKeyUsesAssetIdentityNotCASKey(t *testing.T) {
	got := BuildContentMediaPublicSliceKey(
		"video",
		"mas_video_001",
		3,
		"video/mp4",
	)
	const want = "media/video/s/asset/mas_video_001/v3/source.mp4"
	if got != want {
		t.Fatalf("unexpected content public slice key: got %q want %q", got, want)
	}
	if strings.Contains(got, "objects") || strings.Contains(got, "sha256") {
		t.Fatalf("public slice key must not expose a CAS path: %q", got)
	}
	if got := BuildContentMediaPublicSliceKey(
		"image",
		"mas bad",
		1,
		"image/jpeg",
	); got != "" {
		t.Fatalf("invalid asset identity must not produce a public slice: %q", got)
	}
	unicodeAsset := BuildContentMediaPublicSliceKey(
		"image",
		"杭州西湖_cover_三潭印月",
		1,
		"image/jpeg",
	)
	if !strings.HasPrefix(unicodeAsset, "media/image/s/asset/unicode-") ||
		!strings.HasSuffix(unicodeAsset, "/v1/source.jpg") {
		t.Fatalf("historical unicode asset must receive a stable public path: %q", unicodeAsset)
	}
	if got := BuildContentMediaPublicSliceKey(
		"avatar",
		"creator_avatar_001",
		1,
		"image/png",
	); got != "media/avatar/s/asset/creator_avatar_001/v1/source.png" {
		t.Fatalf("avatar public slice kind drift: %q", got)
	}
}
