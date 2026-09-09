// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
// 无类别 release 使用公开 slice，保留 sources 原始权利与单源资产绑定。
package local_contract

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	releaseimport "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/infrastructure/releaseimport"
)

func TestLoadCreatorsKeepsRightsRecordsWithPublicAvatarBinding(t *testing.T) {
	root := creatorReleaseFixture(t)
	rightsPath := filepath.Join(root, "payload", "objects", "creators", testCreatorID, "sources", "avatar", "source.json")
	raw, err := os.ReadFile(rightsPath)
	if err != nil {
		t.Fatal(err)
	}
	var source map[string]any
	if err := json.Unmarshal(raw, &source); err != nil {
		t.Fatal(err)
	}
	source["assets"] = []map[string]any{{"assetId": "original-avatar", "rightsStatus": "unverified", "distributionDecision": "research_allowed", "usageScope": "research", "authorizationRequired": true}}
	rights, err := json.Marshal(source)
	if err != nil {
		t.Fatal(err)
	}
	writeReleaseTestFile(t, rightsPath, string(rights))
	_, creators, err := releaseimport.LoadCreatorsForRelease(root, "https://avatar.example.com")
	if err != nil {
		t.Fatal(err)
	}
	if len(creators) != 1 {
		t.Fatalf("unexpected creators: %+v", creators)
	}
	profile := creators[0].Profile
	if profile.AvatarPublicSliceKey == "" || !strings.HasPrefix(profile.AvatarURL, "https://avatar.example.com/"+profile.AvatarPublicSliceKey) || strings.Contains(profile.AvatarURL, "media/objects/") {
		t.Fatalf("avatar must use the canonical public slice: %+v", profile)
	}
	if profile.AvatarAsset == nil || profile.AvatarAsset.AssetID != testAvatarID || profile.AvatarAsset.AssetID == profile.PersonaID {
		t.Fatalf("avatar identity must come from the release media manifest: %+v", profile.AvatarAsset)
	}
	gotRights, err := os.ReadFile(rightsPath)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(gotRights, rights) {
		t.Fatal("public delivery must not rewrite immutable source rights records")
	}
}

func TestLoadCreatorsRejectsRetiredPrivateReleaseAvatar(t *testing.T) {
	root := creatorReleaseFixture(t)
	manifestPath := filepath.Join(root, "payload", "media_manifest.json")
	raw, err := os.ReadFile(manifestPath)
	if err != nil {
		t.Fatal(err)
	}
	var document map[string]any
	if err := json.Unmarshal(raw, &document); err != nil {
		t.Fatal(err)
	}
	asset := document["assets"].([]any)[0].(map[string]any)
	delete(asset, "publicSliceKey")
	asset["privateObjectKey"] = "media/objects/sha256/aa/bb/private.jpg"
	raw, err = json.Marshal(document)
	if err != nil {
		t.Fatal(err)
	}
	writeReleaseTestFile(t, manifestPath, string(raw))
	_, _, err = releaseimport.LoadCreatorsForRelease(root, "https://avatar.example.com")
	if err == nil || !strings.Contains(err.Error(), `unknown field "privateObjectKey"`) {
		t.Fatalf("retired private release delivery must fail closed, err=%v", err)
	}
}

func TestLoadCreatorsLeavesAvatarBindingAbsentWithoutAvatarAsset(t *testing.T) {
	root := creatorReleaseFixture(t)
	profilePath := filepath.Join(root, "payload", "objects", "creators", testCreatorID, "profile.json")
	raw, err := os.ReadFile(profilePath)
	if err != nil {
		t.Fatal(err)
	}
	var document map[string]any
	if err := json.Unmarshal(raw, &document); err != nil {
		t.Fatal(err)
	}
	// 只取消展示头像；保留 owner 的非空采用资产与完整来源闭包。
	delete(document, "avatarAsset")
	raw, err = json.Marshal(document)
	if err != nil {
		t.Fatal(err)
	}
	writeReleaseTestFile(t, profilePath, string(raw))
	_, creators, err := releaseimport.LoadCreatorsForRelease(root, "https://avatar.example.com")
	if err != nil || len(creators) != 1 {
		t.Fatalf("load creator without avatar: creators=%v err=%v", creators, err)
	}
	profile := creators[0].Profile
	if profile.AvatarAsset != nil || profile.AvatarURL != "" || profile.AvatarVersion != 0 || profile.AvatarPublicSliceKey != "" {
		t.Fatalf("absent avatar asset must keep binding absent, got %+v", profile)
	}
}
