package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestRemoveUntrackedGeneratedOutputsRemovesRetiredSingleTrackOutputs(t *testing.T) {
	appDir := t.TempDir()
	beginGeneratedManifestForTest(t, appDir, "canonical-graph")
	retired := []string{
		"lib/cloud/user/generated/prefab_user_metadata.g.dart",
		"lib/cloud/runtime/generated/circle/circle_detail_wire_dto.dart",
		"lib/cloud/runtime/generated/circle/circle_dto.dart",
		"lib/cloud/runtime/generated/circle/circle_dtos.dart",
		"lib/cloud/runtime/generated/circle/circle_member_dto.dart",
		"lib/cloud/runtime/generated/circle/circle_member_roster_item_dto.dart",
		"lib/cloud/runtime/generated/circle/circle_section_config_dto.dart",
		"lib/cloud/runtime/generated/content/content_app_config_client_dto.g.dart",
		"lib/cloud/runtime/generated/content/content_dtos.dart",
		"lib/cloud/runtime/generated/entity/homepage_models.dart",
		"lib/cloud/runtime/generated/integration/location_poi_dto.g.dart",
		"lib/cloud/runtime/generated/recommendation/feed_realtime_patch.g.dart",
		"lib/cloud/runtime/generated/rtc/rtc_signal_payloads.g.dart",
		"packages/quwoquan_cloud_contracts/lib/src/generated/assistant/assistant_run_envelope.g.dart",
		"packages/quwoquan_cloud_contracts/lib/src/rtc/call_session_dtos.g.dart",
		"packages/quwoquan_cloud_contracts/lib/src/generated/chat_contract_enums.g.dart",
		"packages/quwoquan_cloud_contracts/lib/src/generated/circle_contract_enums.g.dart",
		"packages/quwoquan_cloud_contracts/lib/src/generated/content_contract_enums.g.dart",
		"packages/quwoquan_cloud_contracts/lib/src/generated/homepage_type.g.dart",
		"packages/quwoquan_cloud_contracts/lib/src/generated/user_contract_enums.g.dart",
		"packages/quwoquan_cloud_contracts/lib/src/generated/requests/integration/location_queries.requests.g.dart",
		"packages/quwoquan_cloud_contracts/lib/src/generated/requests/notification/app_message_contracts.requests.g.dart",
		"packages/quwoquan_cloud_contracts/lib/src/generated/requests/notification/incoming_call_delivery_contracts.requests.g.dart",
	}
	for _, relativePath := range retired {
		path := filepath.Join(appDir, filepath.FromSlash(relativePath))
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatalf("create generated directory for %s: %v", relativePath, err)
		}
		if err := os.WriteFile(
			path,
			[]byte("// Code generated from retired single-track source. DO NOT EDIT.\n"),
			0o600,
		); err != nil {
			t.Fatalf("write retired generated output %s: %v", relativePath, err)
		}
	}

	if err := removeUntrackedGeneratedOutputs(); err != nil {
		t.Fatal(err)
	}

	for _, relativePath := range retired {
		path := filepath.Join(appDir, filepath.FromSlash(relativePath))
		if _, err := os.Stat(path); !os.IsNotExist(err) {
			t.Fatalf("retired output %s must be removed, stat error: %v", relativePath, err)
		}
	}
}

func TestRetiredSingleTrackOwnersRemainPhysicallyAbsent(t *testing.T) {
	appDir := filepath.Clean("../../../quwoquan_app")
	for _, relativePath := range []string{
		"packages/quwoquan_cloud_contracts/lib/src/content/content_post_projection.dart",
		"packages/quwoquan_cloud_contracts/lib/src/content/entity_wishlist_state.dart",
	} {
		path := filepath.Join(appDir, filepath.FromSlash(relativePath))
		if _, err := os.Stat(path); !os.IsNotExist(err) {
			t.Errorf("retired handwritten model owner still exists: %s", path)
		}
	}

	for _, generatorPath := range []string{
		"circle_contract_enum_codegen.go",
		"content_app_config_client_codegen.go",
		"content_dtos_barrel_codegen.go",
		"rtc_call_session_dto_codegen.go",
		"rtc_dto_emit.go",
	} {
		if _, err := os.Stat(generatorPath); !os.IsNotExist(err) {
			t.Errorf("retired standalone generator still exists: %s", generatorPath)
		}
	}
}
