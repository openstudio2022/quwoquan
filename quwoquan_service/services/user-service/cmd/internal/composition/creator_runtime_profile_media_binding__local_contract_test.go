// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
//
// creator release 头像只使用 public slice；存在资产身份但缺少公开绑定时拒绝，
// 不把旧私有交付或缺席值解释为 public。
package composition

import (
	"context"
	"testing"

	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
	creatormodel "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/domain/model"
)

// stubCreatorRuntimeProfileReader 是对象级 typed double，只回放注入的存储投影。
type stubCreatorRuntimeProfileReader struct {
	profile *creatormodel.CreatorRuntimeProfile
}

func (s *stubCreatorRuntimeProfileReader) FindByExactContentFence(
	context.Context,
	creatormodel.ReleaseIdentity,
	string,
) (*creatormodel.CreatorRuntimeProfile, bool, error) {
	return s.profile, s.profile != nil, nil
}

func findCreatorView(
	t *testing.T,
	profile *creatormodel.CreatorRuntimeProfile,
) (assetID string, accessMode string) {
	t.Helper()
	adapter := NewCreatorRuntimeProfileAdapter(
		&stubCreatorRuntimeProfileReader{profile: profile},
	)
	view, found, err := adapter.FindByExactContentFence(
		context.Background(),
		userports.ContentReleaseFence{Environment: "alpha", SourceOwner: "qwq_data", ReleaseID: "release-a", ManifestDigest: "sha256:" + repeatHex64()},
		profile.PersonaID,
	)
	if err != nil || !found || view == nil {
		t.Fatalf("creator view lookup failed: found=%v err=%v", found, err)
	}
	return view.AvatarAssetID, view.AvatarAccessMode
}

func TestCreatorViewRejectsRetiredPrivateAvatarBinding(t *testing.T) {
	adapter := NewCreatorRuntimeProfileAdapter(&stubCreatorRuntimeProfileReader{
		profile: &creatormodel.CreatorRuntimeProfile{
			CreatorID: "creator-a", PersonaID: "author-a",
			AvatarURL:     "media/objects/sha256/aa/aa/" + repeatHex64() + ".jpg",
			AvatarAssetID: "avatar-a",
		},
	})
	view, found, err := adapter.FindByExactContentFence(
		context.Background(),
		userports.ContentReleaseFence{Environment: "alpha", SourceOwner: "qwq_data", ReleaseID: "release-a", ManifestDigest: "sha256:" + repeatHex64()},
		"author-a",
	)
	if err == nil || found || view != nil {
		t.Fatalf("missing public binding must fail closed: view=%v found=%v err=%v", view, found, err)
	}
}

func TestCreatorViewDerivesPublicForProductionAvatarBinding(t *testing.T) {
	assetID, accessMode := findCreatorView(t, &creatormodel.CreatorRuntimeProfile{
		CreatorID: "creator-a", PersonaID: "author-a",
		AvatarURL:            "https://avatar.example.com/media/avatar/s/asset/avatar-a/v1/source.jpg",
		AvatarAssetID:        "avatar-a",
		AvatarPublicSliceKey: "media/avatar/s/asset/avatar-a/v1/source.jpg",
	})
	if assetID != "avatar-a" || accessMode != mediaDeliveryAccessModePublic {
		t.Fatalf(
			"production avatar binding must expose assetId with public, got assetId=%q accessMode=%q",
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
