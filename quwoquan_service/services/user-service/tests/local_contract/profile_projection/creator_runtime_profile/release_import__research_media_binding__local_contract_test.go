// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
//
// 无类别 release 的头像只绑定 canonical public slice 与真实资产身份；
// 权利记录原样保留，头像缺席时不得补造交付身份。
package local_contract

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

	releaseimport "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/infrastructure/releaseimport"
)

func TestLoadCreatorsKeepsRightsRecordsWithPublicAvatarBinding(t *testing.T) {
	root := creatorReleaseFixture(t)
	rightsPath := filepath.Join(root, "payload", "objects", "creators", testCreatorID, "rights_snapshots", "avatar.json")
	rights := []byte(`{"assetId":"avatar-a","rightsStatus":"unverified","distributionDecision":"research_allowed","usageScope":"research","authorizationRequired":true,"manifestAsset":{"assetId":"avatar-a","sha256":"` + testAvatarSHA + `"}}`)
	writeReleaseTestFile(t, rightsPath, string(rights))
	_, creators, err := releaseimport.LoadCreatorsForRelease(root, "https://avatar.example.com")
	if err != nil {
		t.Fatal(err)
	}
	if len(creators) != 1 {
		t.Fatalf("unexpected creators: %+v", creators)
	}
	profile := creators[0].Profile
	if profile.AvatarPublicSliceKey == "" ||
		!strings.HasPrefix(profile.AvatarURL, "https://avatar.example.com/"+profile.AvatarPublicSliceKey) ||
		strings.Contains(profile.AvatarURL, "media/objects/") {
		t.Fatalf("avatar must use the canonical public slice: %+v", profile)
	}
	if profile.AvatarAsset == nil ||
		profile.AvatarAsset.AssetID != testAvatarID ||
		profile.AvatarAsset.AssetID == profile.PersonaID {
		t.Fatalf("avatar identity must come from the release media manifest: %+v", profile.AvatarAsset)
	}
	gotRights, err := os.ReadFile(rightsPath)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(gotRights, rights) {
		t.Fatal("public delivery must not rewrite immutable rights records")
	}
}

func TestLoadCreatorsRejectsRetiredPrivateReleaseAvatar(t *testing.T) {
	root := creatorReleaseFixture(t)
	writeReleaseTestFile(
		t,
		filepath.Join(root, "payload", "media_manifest.json"),
		`{"schema":"quwoquan_data.release_media_manifest","releaseId":"release-a","sourceOwner":"qwq_data","assets":[{"assetId":"avatar-a","kind":"avatar","version":1,"contentType":"image/jpeg","privateObjectKey":"media/objects/sha256/aa/aa/`+strings.TrimPrefix(testAvatarSHA, "sha256:")+`.jpg","sha256":"`+testAvatarSHA+`","bytes":12,"ownerRefs":["creators/creator-a"],"rightsSnapshotRefs":["objects/creators/creator-a/rights_snapshots/avatar.json"]}],"issues":[],"counts":{"assets":1,"issues":0}}`,
	)
	_, _, err := releaseimport.LoadCreatorsForRelease(root, "https://avatar.example.com")
	if err == nil || !strings.Contains(err.Error(), `unknown field "privateObjectKey"`) {
		t.Fatalf("retired private release delivery must fail closed, err=%v", err)
	}
}

func TestLoadCreatorsLeavesAvatarBindingAbsentWithoutAvatarAsset(t *testing.T) {
	root := creatorReleaseFixture(t)
	// 头像资产缺席：profile 不声明 avatarAsset，绑定字段必须整体缺席。
	writeReleaseTestFile(
		t,
		filepath.Join(root, "payload", "objects", "creators", testCreatorID, "profile.json"),
		`{"schema":"quwoquan_data.creator_profile","creatorId":"creator-a","userId":"author-a","authorId":"author-a","personaId":"author-a","displayName":"Creator A","userHandle":"creator_a","headline":"headline","bio":"bio","creatorArchetype":"guide","publicProfileTagRefs":[]}`,
	)
	_, creators, err := releaseimport.LoadCreatorsForRelease(root, "https://avatar.example.com")
	if err != nil {
		t.Fatal(err)
	}
	if len(creators) != 1 {
		t.Fatalf("unexpected creators: %+v", creators)
	}
	profile := creators[0].Profile
	if profile.AvatarAsset != nil || profile.AvatarURL != "" ||
		profile.AvatarVersion != 0 || profile.AvatarPublicSliceKey != "" {
		t.Fatalf("absent avatar asset must keep binding absent, got %+v", profile)
	}
}
