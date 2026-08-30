// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
//
// research release 导入 creator 头像的媒体交付绑定（DEC-033）：avatarUrl 落
// release authority 的相对 CAS key、publicSliceKey 缺席，avatarAssetId 只取
// release payload 媒体清单的真实资产标识（禁止以 personaId 冒充）；头像资产
// 缺席时全部绑定字段一并缺席，importer 不得造值。
package local_contract

import (
	"path/filepath"
	"strings"
	"testing"

	releaseimport "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/infrastructure/releaseimport"
)

// researchCreatorReleaseFixture 把 commercial fixture 改写为 research 交付：
// release header releaseClass=research，媒体清单只带绑定 sha256 的相对
// privateObjectKey（DEC-031 单一交付身份，不得同时有 publicSliceKey）。
func researchCreatorReleaseFixture(t *testing.T) (string, string) {
	t.Helper()
	root := creatorReleaseFixture(t)
	digest := strings.TrimPrefix(testAvatarSHA, "sha256:")
	casKey := "media/objects/sha256/" +
		digest[:2] + "/" + digest[2:4] + "/" + digest + ".jpg"
	writeReleaseTestFile(
		t,
		filepath.Join(root, "payload", "release.json"),
		`{"schema":"quwoquan_data.release","releaseId":"release-a","releaseClass":"research"}`,
	)
	writeReleaseTestFile(
		t,
		filepath.Join(root, "payload", "media_manifest.json"),
		`{"schema":"quwoquan_data.release_media_manifest","releaseId":"release-a","sourceOwner":"qwq_data","assets":[{"assetId":"avatar-a","kind":"avatar","version":1,"contentType":"image/jpeg","privateObjectKey":"`+casKey+`","sha256":"`+testAvatarSHA+`","bytes":12,"ownerRefs":["creators/creator-a"],"rightsSnapshotRefs":["objects/creators/creator-a/rights_snapshots/avatar.json"]}],"issues":[],"counts":{"assets":1,"issues":0}}`,
	)
	return root, casKey
}

func TestLoadCreatorsBindsResearchAvatarToRelativeCASKey(t *testing.T) {
	root, casKey := researchCreatorReleaseFixture(t)
	_, creators, err := releaseimport.LoadCreatorsForRelease(
		root,
		"https://avatar.example.com",
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(creators) != 1 {
		t.Fatalf("unexpected creators: %+v", creators)
	}
	profile := creators[0].Profile
	if profile.AvatarURL != casKey ||
		strings.HasPrefix(profile.AvatarURL, "http") {
		t.Fatalf(
			"research avatar delivery must be the relative CAS key, got %q",
			profile.AvatarURL,
		)
	}
	if profile.AvatarPublicSliceKey != "" {
		t.Fatalf(
			"research avatar must not carry a public slice key, got %q",
			profile.AvatarPublicSliceKey,
		)
	}
	if profile.AvatarAsset == nil ||
		profile.AvatarAsset.AssetID != testAvatarID ||
		profile.AvatarAsset.AssetID == profile.PersonaID {
		t.Fatalf(
			"avatar asset identity must come from the release media manifest, got %+v",
			profile.AvatarAsset,
		)
	}
}

func TestLoadCreatorsLeavesAvatarBindingAbsentWithoutAvatarAsset(t *testing.T) {
	root, _ := researchCreatorReleaseFixture(t)
	// 头像资产缺席：profile 不声明 avatarAsset，绑定字段必须整体缺席。
	writeReleaseTestFile(
		t,
		filepath.Join(root, "payload", "objects", "creators", testCreatorID, "profile.json"),
		`{"schema":"quwoquan_data.creator_profile","creatorId":"creator-a","userId":"author-a","authorId":"author-a","personaId":"author-a","displayName":"Creator A","userHandle":"creator_a","headline":"headline","bio":"bio","creatorArchetype":"guide","publicProfileTagRefs":[]}`,
	)
	_, creators, err := releaseimport.LoadCreatorsForRelease(
		root,
		"https://avatar.example.com",
	)
	if err != nil {
		t.Fatal(err)
	}
	profile := creators[0].Profile
	if profile.AvatarAsset != nil ||
		profile.AvatarURL != "" ||
		profile.AvatarPublicSliceKey != "" {
		t.Fatalf("absent avatar asset must keep binding absent, got %+v", profile)
	}
}
