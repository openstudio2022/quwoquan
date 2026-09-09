// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
package local_contract

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	releaseimport "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/infrastructure/releaseimport"
)

func TestLoadCreatorsRejectsRetiredReleaseHeaders(t *testing.T) {
	for _, fields := range []string{
		`"releaseClass":"research"`,
		`"releaseClass":"commercial"`,
		`"releaseClass":null`,
		`"releaseClass":"production","class":null`,
		`"releaseClass":"production","privateObjectKey":""`,
	} {
		t.Run(fields, func(t *testing.T) {
			root := creatorReleaseFixture(t)
			writeReleaseTestFile(t, filepath.Join(root, "payload", "release.json"),
				`{"schema":"quwoquan_data.release","releaseId":"release-a","sourceOwner":"qwq_data","releaseKind":"content",`+fields+`}`)
			_, creators, err := releaseimport.LoadCreatorsForRelease(root, "https://avatar.example.com")
			if err == nil || len(creators) != 0 {
				t.Fatalf("retired header must fail closed: creators=%v err=%v", creators, err)
			}
		})
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
	if profile.AvatarAsset != nil || profile.AvatarURL != "" || profile.AvatarPublicSliceKey != "" {
		t.Fatalf("absent avatar asset must keep binding absent, got %+v", profile)
	}
}
