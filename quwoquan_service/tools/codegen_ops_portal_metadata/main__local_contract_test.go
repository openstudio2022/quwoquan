package main

import (
	"path/filepath"
	"testing"

	"quwoquan_service/internal/metadata/validate"
)

func TestPortalMenuHasNoRegistrationOrOnboardingSurface(t *testing.T) {
	metadataDir := filepath.Join("..", "..", "contracts", "metadata")
	source, err := compileContractSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		t.Fatalf("compile metadata: %v", err)
	}
	menu := readYAML[portalMenuFile](source, filepath.Join("_control_plane", "portal_menu.yaml"))
	for _, item := range menu.Menus {
		if item.MenuID == "platform-onboarding" || item.RoutePath == "/platform/onboarding" {
			t.Fatalf("manual onboarding surface remains: %+v", item)
		}
	}
}
