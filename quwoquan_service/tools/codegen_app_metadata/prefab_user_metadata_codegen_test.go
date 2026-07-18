package main

import (
	"strings"
	"testing"
)

func TestRenderPrefabUserMetadataDart(t *testing.T) {
	t.Parallel()

	rendered := renderPrefabUserMetadataDart(&prefabUserProvenance{
		CurrentUser: prefabCurrentUser{
			UserID:       "fixture_user_current",
			SubAccountID: "fixture_persona_daily",
		},
	})

	for _, expected := range []string{
		"from _shared/prefab_user_provenance.yaml",
		`static const String currentUserId = "fixture_user_current";`,
		`static const String currentSubAccountId = "fixture_persona_daily";`,
	} {
		if !strings.Contains(rendered, expected) {
			t.Fatalf("generated Dart missing %q:\n%s", expected, rendered)
		}
	}
}
