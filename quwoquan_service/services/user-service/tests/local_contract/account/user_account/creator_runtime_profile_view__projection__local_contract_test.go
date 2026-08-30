package local_contract

import (
	"encoding/json"
	"strings"
	"testing"

	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

func TestCreatorRuntimeProfilePublicViewExposesOnlyDeliveryReference(t *testing.T) {
	view := application.BuildCreatorRuntimeProfileView(&userports.CreatorRuntimeProfileView{
		CreatorID:     "creator-a",
		PersonaID:     "author-a",
		AvatarURL:     "https://avatar.example.com/media/avatar/s/asset/avatar-a/v1/source.jpg",
		AvatarVersion: 1,
	})
	raw, err := json.Marshal(view)
	if err != nil {
		t.Fatal(err)
	}
	payload := string(raw)
	if !strings.Contains(payload, "https://avatar.example.com/media/avatar/s/asset/") {
		t.Fatalf("public avatar delivery reference missing: %s", payload)
	}
	// avatarAssetId/avatarAccessMode 是契约 PUBLIC/read 的交付绑定字段
	// （DEC-033），公开视图允许在场；存量 public 交付（无绑定来源）出 null。
	if view["avatarAssetId"] != nil || view["avatarAccessMode"] != nil {
		t.Fatalf("legacy public delivery must project null bindings: %s", payload)
	}
	for _, forbidden := range []string{
		"avatarVersion",
		"userId",
		"avatarPublicSliceKey",
		"avatarSha256",
		"avatarObjectKey",
		"objects/sha256",
	} {
		if strings.Contains(payload, forbidden) {
			t.Fatalf("public creator profile leaked %q: %s", forbidden, payload)
		}
	}
}

func TestCreatorRuntimeProfileViewProjectsSignedGrantAvatarBinding(t *testing.T) {
	// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
	view := application.BuildCreatorRuntimeProfileView(&userports.CreatorRuntimeProfileView{
		CreatorID:        "creator-b",
		PersonaID:        "author-b",
		AvatarURL:        "media/objects/sha256/aa/bb/" + strings.Repeat("a", 64) + ".jpg",
		AvatarAssetID:    "avatar-asset-b",
		AvatarAccessMode: "signed_grant",
	})
	if view["avatarAssetId"] != "avatar-asset-b" {
		t.Fatalf("avatarAssetId = %v, want avatar-asset-b", view["avatarAssetId"])
	}
	if view["avatarAccessMode"] != "signed_grant" {
		t.Fatalf("avatarAccessMode = %v, want signed_grant", view["avatarAccessMode"])
	}
	// 资产标识不得以 personaId 冒充。
	if view["avatarAssetId"] == view["personaId"] {
		t.Fatal("avatarAssetId must not be forged from personaId")
	}
}
