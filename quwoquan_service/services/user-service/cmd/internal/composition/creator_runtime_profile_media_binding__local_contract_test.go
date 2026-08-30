// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
//
// creator 头像的媒体交付绑定读面派生（DEC-033）：composition 层是
// avatarAccessMode 的唯一派生点，只依据 release-import 按 release authority
// 断言写入的存储事实 avatarPublicSliceKey——commercial 交付必有派生 public
// slice（→ public），research 交付必为空（→ signed_grant）；无资产标识时
// 两字段一并缺席，禁止从 URL 形态反推交付形态（DEC-031）。
package composition

import (
	"context"
	"testing"

	creatormodel "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/domain/model"
)

// stubCreatorRuntimeProfileReader 是对象级 typed double，只回放注入的存储投影。
type stubCreatorRuntimeProfileReader struct {
	profile *creatormodel.CreatorRuntimeProfile
}

func (s *stubCreatorRuntimeProfileReader) FindActiveByPublicIdentity(
	context.Context,
	string,
) (*creatormodel.CreatorRuntimeProfile, bool, error) {
	return s.profile, s.profile != nil, nil
}

func (s *stubCreatorRuntimeProfileReader) ListActiveWorks(
	context.Context,
	string,
) ([]creatormodel.CreatorWorkRef, bool, error) {
	return nil, s.profile != nil, nil
}

func findCreatorView(
	t *testing.T,
	profile *creatormodel.CreatorRuntimeProfile,
) (assetID string, accessMode string) {
	t.Helper()
	adapter := NewCreatorRuntimeProfileAdapter(
		&stubCreatorRuntimeProfileReader{profile: profile},
	)
	view, found, err := adapter.FindActiveByPublicIdentity(
		context.Background(),
		profile.PersonaID,
	)
	if err != nil || !found || view == nil {
		t.Fatalf("creator view lookup failed: found=%v err=%v", found, err)
	}
	return view.AvatarAssetID, view.AvatarAccessMode
}

func TestCreatorViewDerivesSignedGrantForResearchAvatarBinding(t *testing.T) {
	assetID, accessMode := findCreatorView(t, &creatormodel.CreatorRuntimeProfile{
		CreatorID: "creator-a", PersonaID: "author-a",
		// research 导入：avatarUrl 落相对 CAS key，publicSliceKey 为空。
		AvatarURL:     "media/objects/sha256/aa/aa/" + repeatHex64() + ".jpg",
		AvatarAssetID: "avatar-a",
	})
	if assetID != "avatar-a" || accessMode != mediaDeliveryAccessModeSignedGrant {
		t.Fatalf(
			"research avatar binding must expose assetId with signed_grant, got assetId=%q accessMode=%q",
			assetID,
			accessMode,
		)
	}
}

func TestCreatorViewDerivesPublicForCommercialAvatarBinding(t *testing.T) {
	assetID, accessMode := findCreatorView(t, &creatormodel.CreatorRuntimeProfile{
		CreatorID: "creator-a", PersonaID: "author-a",
		AvatarURL:            "https://avatar.example.com/media/avatar/s/asset/avatar-a/v1/source.jpg",
		AvatarAssetID:        "avatar-a",
		AvatarPublicSliceKey: "media/avatar/s/asset/avatar-a/v1/source.jpg",
	})
	if assetID != "avatar-a" || accessMode != mediaDeliveryAccessModePublic {
		t.Fatalf(
			"commercial avatar binding must expose assetId with public, got assetId=%q accessMode=%q",
			assetID,
			accessMode,
		)
	}
}

func TestCreatorViewLeavesAvatarBindingAbsentWithoutAssetIdentity(t *testing.T) {
	assetID, accessMode := findCreatorView(t, &creatormodel.CreatorRuntimeProfile{
		CreatorID: "creator-a", PersonaID: "author-a",
	})
	if assetID != "" || accessMode != "" {
		t.Fatalf(
			"absent avatar asset must keep both fields absent, got assetId=%q accessMode=%q",
			assetID,
			accessMode,
		)
	}
}

func repeatHex64() string {
	digest := make([]byte, 64)
	for index := range digest {
		digest[index] = 'a'
	}
	return string(digest)
}
