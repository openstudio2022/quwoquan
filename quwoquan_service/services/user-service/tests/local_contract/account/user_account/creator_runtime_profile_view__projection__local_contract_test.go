package local_contract

import (
	"encoding/json"
	"strings"
	"testing"

	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	model "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

func TestCreatorRuntimeProfilePublicViewExposesOnlyDeliveryReference(t *testing.T) {
	view := application.BuildCreatorRuntimeProfileView(&model.CreatorRuntimeProfile{
		CreatorID:            "creator-a",
		PersonaID:            "author-a",
		AvatarURL:            "https://avatar.example.com/media/avatar/s/asset/avatar-a/v1/source.jpg",
		AvatarAssetID:        "avatar-a",
		AvatarVersion:        1,
		AvatarPublicSliceKey: "media/avatar/s/asset/avatar-a/v1/source.jpg",
		AvatarSHA256:         "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
	})
	raw, err := json.Marshal(view)
	if err != nil {
		t.Fatal(err)
	}
	payload := string(raw)
	if view["avatarVersion"] != int64(1) ||
		!strings.Contains(payload, "https://avatar.example.com/media/avatar/s/asset/") {
		t.Fatalf("public avatar delivery reference missing: %s", payload)
	}
	for _, forbidden := range []string{
		"avatarAssetId",
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
