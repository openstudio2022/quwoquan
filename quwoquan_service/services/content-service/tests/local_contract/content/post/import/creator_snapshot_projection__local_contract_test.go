package releaseimport_test

import (
	"os"
	"path/filepath"
	"testing"

	releaseimport "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func TestImportedPostProjectsCanonicalCreatorSnapshot(t *testing.T) {
	root := t.TempDir()
	creatorID := "creator-a"
	creatorDir := filepath.Join(root, "creators", creatorID)
	if err := os.MkdirAll(creatorDir, 0o755); err != nil {
		t.Fatal(err)
	}
	profile := `{
		"schema":"quwoquan_data.creator_profile",
		"creatorId":"creator-a",
		"userId":"author-a",
		"authorId":"author-a",
		"displayName":"林间取景",
		"avatarAsset":{
			"assetId":"avatar-a",
			"kind":"avatar",
			"sha256":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
		}
	}`
	if err := os.WriteFile(filepath.Join(creatorDir, "profile.json"), []byte(profile), 0o644); err != nil {
		t.Fatal(err)
	}

	creators, err := releaseimport.LoadCreatorAuthorSnapshots(
		root,
		map[string]bool{creatorID: true},
		map[string]releaseimport.ReleaseMediaAsset{
			"avatar-a": {
				AssetID:            "avatar-a",
				Kind:               "avatar",
				SHA256:             "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
				Version:            1,
				PublicSliceKey:     "media/avatar/s/asset/avatar-a/v1/source.webp",
				OwnerRefs:          []string{"creators/creator-a"},
				RightsSnapshotRefs: []string{"objects/creators/creator-a/rights_snapshots/avatar-a.json"},
			},
		},
		"https://cdn.example.invalid",
	)
	if err != nil {
		t.Fatal(err)
	}
	posts := []releaseimport.PostDoc{{
		PostRef:  "posts/article/攻略/甲/1",
		AuthorID: "author-a",
	}}
	if err := releaseimport.BindPostAuthorSnapshots(posts, creators); err != nil {
		t.Fatal(err)
	}
	if posts[0].AuthorDisplayName != "林间取景" {
		t.Fatalf("author display name snapshot=%q", posts[0].AuthorDisplayName)
	}
	if posts[0].AuthorAvatarURL != "https://cdn.example.invalid/media/avatar/s/asset/avatar-a/v1/source.webp" {
		t.Fatalf("author avatar URL snapshot=%q", posts[0].AuthorAvatarURL)
	}
	if !releaseimport.CreatorAuthorIDs(creators)["author-a"] {
		t.Fatal("creator receipt closure must keep the canonical authorId")
	}
}

func TestImportedPostCreatorSnapshotFailsClosed(t *testing.T) {
	posts := []releaseimport.PostDoc{{
		PostRef:  "posts/article/攻略/甲/1",
		AuthorID: "author-a",
	}}
	if err := releaseimport.BindPostAuthorSnapshots(
		posts,
		map[string]releaseimport.CreatorAuthorSnapshot{},
	); err == nil {
		t.Fatal("missing canonical creator snapshot must fail closed")
	}
}

func TestImportedCreatorAvatarRequiresTypedDeliveryTopology(t *testing.T) {
	root := t.TempDir()
	creatorID := "creator-a"
	creatorDir := filepath.Join(root, "creators", creatorID)
	if err := os.MkdirAll(creatorDir, 0o755); err != nil {
		t.Fatal(err)
	}
	profile := `{
		"schema":"quwoquan_data.creator_profile",
		"creatorId":"creator-a",
		"userId":"author-a",
		"authorId":"author-a",
		"displayName":"林间取景",
		"avatarAsset":{
			"assetId":"avatar-a",
			"kind":"avatar",
			"sha256":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
		}
	}`
	if err := os.WriteFile(filepath.Join(creatorDir, "profile.json"), []byte(profile), 0o644); err != nil {
		t.Fatal(err)
	}

	_, err := releaseimport.LoadCreatorAuthorSnapshots(
		root,
		map[string]bool{creatorID: true},
		map[string]releaseimport.ReleaseMediaAsset{
			"avatar-a": {
				AssetID:            "avatar-a",
				Kind:               "avatar",
				SHA256:             "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
				Version:            1,
				PublicSliceKey:     "media/avatar/s/asset/avatar-a/v1/source.webp",
				OwnerRefs:          []string{"creators/creator-a"},
				RightsSnapshotRefs: []string{"objects/creators/creator-a/rights_snapshots/avatar-a.json"},
			},
		},
		"",
	)
	if err == nil {
		t.Fatal("creator avatar without the typed avatar delivery base must fail closed")
	}
}

func TestImportedCreatorWithoutIndependentAvatarUsesRuntimeFallback(t *testing.T) {
	root := t.TempDir()
	creatorID := "creator-default-avatar"
	creatorDir := filepath.Join(root, "creators", creatorID)
	if err := os.MkdirAll(creatorDir, 0o755); err != nil {
		t.Fatal(err)
	}
	profile := `{
		"schema":"quwoquan_data.creator_profile",
		"creatorId":"creator-default-avatar",
		"userId":"author-default-avatar",
		"authorId":"author-default-avatar",
		"displayName":"默认头像作者"
	}`
	if err := os.WriteFile(filepath.Join(creatorDir, "profile.json"), []byte(profile), 0o644); err != nil {
		t.Fatal(err)
	}

	creators, err := releaseimport.LoadCreatorAuthorSnapshots(
		root,
		map[string]bool{creatorID: true},
		map[string]releaseimport.ReleaseMediaAsset{},
		"",
	)
	if err != nil {
		t.Fatalf("missing independent avatar must not block creator import: %v", err)
	}
	posts := []releaseimport.PostDoc{{
		PostRef:  "posts/article/攻略/默认头像/1",
		AuthorID: "author-default-avatar",
	}}
	if err := releaseimport.BindPostAuthorSnapshots(posts, creators); err != nil {
		t.Fatal(err)
	}
	if posts[0].AuthorAvatarURL != "" {
		t.Fatalf("runtime fallback must remain unbound to release media: %q", posts[0].AuthorAvatarURL)
	}
}
