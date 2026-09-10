package local_contract

import (
	"testing"

	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
func TestPersonaAvatarPreservesCanonicalPathVersion(t *testing.T) {
	for _, raw := range []string{
		"https://cdn.beta.quwoquan.com:18100/media/avatar/s/asset/creator-avatar/v2/source.jpg",
		"https://cdn.quwoquan.com/media/avatar/s/asset/creator-avatar/v2/source.webp",
	} {
		t.Run(raw, func(t *testing.T) {
			view := application.BuildPersonaManagementItem(model.Persona{
				PersonaID: "persona-test", AvatarURL: raw, AvatarVersion: 2,
			})
			if got := view["avatarUrl"]; got != raw {
				t.Fatalf("canonical public slice must remain query-free: got %v, want %s", got, raw)
			}
		})
	}
}

func TestPersonaAvatarUnversionedURLKeepsExplicitVersion(t *testing.T) {
	view := application.BuildPersonaManagementItem(model.Persona{
		PersonaID: "persona-test", AvatarURL: "https://cdn.example.com/avatar.jpg", AvatarVersion: 3,
	})
	if got := view["avatarUrl"]; got != "https://cdn.example.com/avatar.jpg?v=3" {
		t.Fatalf("unversioned avatar cache invalidation changed: %v", got)
	}
}
