package application

import (
	"encoding/json"
	"strings"
	"testing"

	model "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

func TestCreatorRuntimeProfilePublicViewExposesOnlyDeliveryReference(t *testing.T) {
	view := buildCreatorRuntimeProfileView(&model.CreatorRuntimeProfile{
		CreatorID:            "creator-a",
		SubAccountID:         "author-a",
		AvatarURL:            "https://avatar.example.com/media/avatar/s/asset/avatar-a/v2/source.jpg",
		AvatarAssetID:        "avatar-a",
		AvatarVersion:        2,
		AvatarPublicSliceKey: "media/avatar/s/asset/avatar-a/v2/source.jpg",
		AvatarSHA256:         "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
	})
	raw, err := json.Marshal(view)
	if err != nil {
		t.Fatal(err)
	}
	payload := string(raw)
	if view["avatarVersion"] != int64(2) ||
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
