package local_contract

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	runtimemedia "quwoquan_service/runtime/media"
	releaseimport "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/infrastructure/releaseimport"
)

const (
	testCreatorID = "creator-a"
	testAvatarID  = "avatar-a"
	testAvatarSHA = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
)

func writeReleaseTestFile(t *testing.T, path string, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

func creatorReleaseFixture(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	writeReleaseTestFile(
		t,
		filepath.Join(root, "payload", "desired_state.json"),
		`{"schema":"quwoquan_data.release_desired_state","releaseId":"release-a","desiredRefs":{"creators":["creator-a"]}}`,
	)
	writeReleaseTestFile(
		t,
		filepath.Join(root, "payload", "release.json"),
		`{"schema":"quwoquan_data.release","releaseId":"release-a","releaseClass":"commercial"}`,
	)
	creatorRoot := filepath.Join(root, "payload", "objects", "creators", testCreatorID)
	writeReleaseTestFile(
		t,
		filepath.Join(creatorRoot, "profile.json"),
		`{"schema":"quwoquan_data.creator_profile","creatorId":"creator-a","userId":"author-a","authorId":"author-a","personaId":"author-a","displayName":"Creator A","userHandle":"creator_a","avatarAsset":{"assetId":"avatar-a","kind":"avatar","sha256":"`+testAvatarSHA+`"},"headline":"headline","bio":"bio","creatorArchetype":"guide","publicProfileTagRefs":[]}`,
	)
	writeReleaseTestFile(t, filepath.Join(creatorRoot, "works.refs.ndjson"), "")
	publicSlice := runtimemedia.BuildContentMediaPublicSliceKey(
		"avatar",
		testAvatarID,
		1,
		"image/jpeg",
	)
	writeReleaseTestFile(
		t,
		filepath.Join(root, "payload", "media_manifest.json"),
		`{"schema":"quwoquan_data.release_media_manifest","releaseId":"release-a","sourceOwner":"qwq_data","assets":[{"assetId":"avatar-a","kind":"avatar","version":1,"contentType":"image/jpeg","publicSliceKey":"`+publicSlice+`","sha256":"`+testAvatarSHA+`","bytes":12,"ownerRefs":["creators/creator-a"],"rightsSnapshotRefs":["objects/creators/creator-a/rights_snapshots/avatar.json"]}],"issues":[],"counts":{"assets":1,"issues":0}}`,
	)
	writeReleaseTestFile(
		t,
		filepath.Join(
			root,
			"payload",
			"objects",
			"creators",
			testCreatorID,
			"rights_snapshots",
			"avatar.json",
		),
		`{"assetId":"avatar-a","manifestAsset":{"assetId":"avatar-a","sha256":"`+
			testAvatarSHA+`"}}`,
	)
	return root
}

func TestLoadCreatorsResolvesAvatarFromReleaseMediaAuthority(t *testing.T) {
	root := creatorReleaseFixture(t)
	state, creators, err := releaseimport.LoadCreatorsForRelease(
		root,
		"https://avatar.example.com",
	)
	if err != nil {
		t.Fatal(err)
	}
	if state.ReleaseID != "release-a" || len(creators) != 1 {
		t.Fatalf("unexpected release creators: state=%+v creators=%+v", state, creators)
	}
	profile := creators[0].Profile
	if profile.AvatarAsset == nil ||
		profile.AvatarAsset.AssetID != testAvatarID ||
		profile.AvatarVersion != 1 ||
		profile.AvatarPublicSliceKey == "" ||
		!strings.HasPrefix(
			profile.AvatarURL,
			"https://avatar.example.com/media/avatar/s/asset/avatar-a/v1/source.jpg",
		) ||
		strings.Contains(profile.AvatarURL, "objects/sha256") {
		t.Fatalf("avatar binding is not public-safe: %+v", profile)
	}
}

func TestLoadCreatorsRejectsRetiredAndInconsistentAvatarBindings(t *testing.T) {
	tests := []struct {
		name        string
		mutate      func(profile map[string]any, manifest map[string]any)
		errorMarker string
	}{
		{
			name: "retired-avatar-object-key",
			mutate: func(profile map[string]any, _ map[string]any) {
				profile["avatarObjectKey"] = "media/objects/sha256/aa/bb/private.jpg"
			},
			errorMarker: "forbidden avatar objectKey",
		},
		{
			name: "nested-object-key",
			mutate: func(profile map[string]any, _ map[string]any) {
				profile["avatarAsset"].(map[string]any)["objectKey"] = "media/objects/private"
			},
			errorMarker: "forbidden avatar objectKey",
		},
		{
			name: "kind",
			mutate: func(profile map[string]any, _ map[string]any) {
				profile["avatarAsset"].(map[string]any)["kind"] = "image"
			},
			errorMarker: "kind differs",
		},
		{
			name: "sha256",
			mutate: func(profile map[string]any, _ map[string]any) {
				profile["avatarAsset"].(map[string]any)["sha256"] =
					"sha256:" + strings.Repeat("b", 64)
			},
			errorMarker: "sha256 differs",
		},
		{
			name: "owner",
			mutate: func(_ map[string]any, manifest map[string]any) {
				manifest["assets"].([]any)[0].(map[string]any)["ownerRefs"] =
					[]any{"creators/other"}
			},
			errorMarker: "ownerRefs",
		},
		{
			name: "rights",
			mutate: func(_ map[string]any, manifest map[string]any) {
				manifest["assets"].([]any)[0].(map[string]any)["rightsSnapshotRefs"] =
					[]any{"objects/creators/other/rights_snapshots/avatar.json"}
			},
			errorMarker: "rightsSnapshotRefs",
		},
		{
			name: "private-cas-in-release-authority",
			mutate: func(_ map[string]any, manifest map[string]any) {
				manifest["assets"].([]any)[0].(map[string]any)["objectKey"] =
					"media/objects/sha256/aa/bb/private.jpg"
			},
			errorMarker: "unknown field",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			root := creatorReleaseFixture(t)
			profilePath := filepath.Join(
				root,
				"payload",
				"objects",
				"creators",
				testCreatorID,
				"profile.json",
			)
			manifestPath := filepath.Join(root, "payload", "media_manifest.json")
			var profile map[string]any
			var manifest map[string]any
			profileRaw, err := os.ReadFile(profilePath)
			if err != nil {
				t.Fatal(err)
			}
			manifestRaw, err := os.ReadFile(manifestPath)
			if err != nil {
				t.Fatal(err)
			}
			if err := json.Unmarshal(profileRaw, &profile); err != nil {
				t.Fatal(err)
			}
			if err := json.Unmarshal(manifestRaw, &manifest); err != nil {
				t.Fatal(err)
			}
			test.mutate(profile, manifest)
			mutatedProfile, _ := json.Marshal(profile)
			mutatedManifest, _ := json.Marshal(manifest)
			writeReleaseTestFile(t, profilePath, string(mutatedProfile))
			writeReleaseTestFile(t, manifestPath, string(mutatedManifest))
			_, _, err = releaseimport.LoadCreatorsForRelease(
				root,
				"https://avatar.example.com",
			)
			if err == nil || !strings.Contains(err.Error(), test.errorMarker) {
				t.Fatalf("%s must fail closed, err=%v", test.name, err)
			}
		})
	}
}
