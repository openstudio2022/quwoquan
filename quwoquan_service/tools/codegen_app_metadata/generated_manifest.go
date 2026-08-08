package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

var appGeneratedOutputRoots = []string{
	"lib/service/assistant_service/assistant/assistant_preference/domain/generated",
	"lib/service/assistant_service/assistant/assistant_run/domain/generated",
	"lib/service/assistant_service/assistant/assistant_turn_view/domain/generated",
	"lib/service/circle_service/circle_management/circle/presentation/generated",
	"lib/service/content_service/content/post/adapters/generated",
	"lib/service/content_service/content/post/application/generated",
	"lib/service/content_service/content/post/application/public/generated",
	"lib/service/content_service/content/post/domain/generated",
	"lib/service/content_service/content/post/presentation/generated",
	"lib/service/content_service/media/media_asset/application/generated",
	"lib/service/content_service/media/media_upload_session/application/generated",
	"lib/service/entity_service/entity_homepage/homepage/presentation/generated",
	"lib/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/generated",
	"lib/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/generated",
	"lib/runtime/errors/generated",
	"lib/runtime/transport/generated",
	"lib/service/search_service/search/search_index_view/application/generated",
	"lib/service/search_service/search/search_index_view/presentation/generated",
	"lib/service/user_service/account/user_account/application/public/generated",
	"packages/quwoquan_cloud_contracts/lib/src/generated",
	"packages/quwoquan_cloud_contracts/lib/generated",
}

// appGeneratedExactOutputs share directories with outputs owned by another
// generator or maintained outside this emitter. Keeping them exact prevents
// stale-output cleanup from deleting independent generated siblings.
var appGeneratedExactOutputs = []string{
	"lib/runtime/observability/generated/app_telemetry_catalog.g.dart",
	"packages/quwoquan_cloud_contracts/lib/src/rtc/rtc_operation_contracts.g.dart",
}

// appRetiredGeneratedOutputRoots are scanned only so a fresh single-track
// generation can remove outputs from roots that no longer have an owner. They
// are deliberately not legal destinations for newly emitted files.
var appRetiredGeneratedOutputRoots = []string{
	"lib/app/navigation/generated",
	"lib/application/content/media/generated",
	"lib/assistant",
	"lib/cloud/assistant/generated",
	"lib/cloud/chat/generated",
	"lib/cloud/circle/generated",
	"lib/cloud/entity/generated",
	"lib/cloud/rtc/generated",
	"lib/cloud/user/generated",
}

// appRetiredGeneratedExactOutputs share a still-active legacy root with
// artifacts whose ownership is outside this direct-path cutover. Scanning
// exact files prevents the next single-track generation from deleting mixed,
// packaged, or separately retired outputs in those roots.
var appRetiredGeneratedExactOutputs = []string{
	"lib/service/content_service/content/post/adapters/generated/content_post_immersive_wire_keys.g.dart",
	"lib/service/content_service/content/post/application/generated/content_metadata.g.dart",
	"lib/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/generated/intersection_kind_metadata.g.dart",
	"lib/service/search_service/search/search_index_view/application/generated/search_contract.g.dart",
	"lib/service/search_service/search/search_index_view/application/generated/search_registry.g.dart",
	"lib/cloud/content/generated/content_behaviors.g.dart",
	"lib/cloud/content/generated/content_errors.g.dart",
	"lib/cloud/content/generated/content_privacy_policy.g.dart",
	"lib/cloud/content/generated/content_publication_policy.g.dart",
	"lib/cloud/content/generated/content_ui_config.g.dart",
	"lib/cloud/runtime/generated/app_request_page_ids.g.dart",
	"lib/cloud/runtime/generated/cloud_api_defaults.g.dart",
	"lib/cloud/runtime/generated/assistant/assistant_api_metadata.g.dart",
	"lib/cloud/runtime/generated/assistant/assistant_request_page_ids.g.dart",
	"lib/cloud/runtime/generated/auth/auth_policy.g.dart",
	"lib/cloud/runtime/generated/chat/chat_api_metadata.g.dart",
	"lib/cloud/runtime/generated/chat/chat_request_page_ids.g.dart",
	"lib/cloud/runtime/generated/circle/circle_api_metadata.g.dart",
	"lib/cloud/runtime/generated/circle/circle_category_tab_config_dto.dart",
	"lib/cloud/runtime/generated/circle/circle_category_tab_defaults.dart",
	"lib/cloud/runtime/generated/circle/circle_category_tab_order.dart",
	"lib/cloud/runtime/generated/circle/circle_detail_wire_dto.dart",
	"lib/cloud/runtime/generated/circle/circle_dto.dart",
	"lib/cloud/runtime/generated/circle/circle_dtos.dart",
	"lib/cloud/runtime/generated/circle/circle_member_dto.dart",
	"lib/cloud/runtime/generated/circle/circle_member_roster_item_dto.dart",
	"lib/cloud/runtime/generated/circle/circle_request_page_ids.g.dart",
	"lib/cloud/runtime/generated/circle/circle_section_config_dto.dart",
	"lib/cloud/runtime/generated/circle/circle_ui_config.g.dart",
	"lib/cloud/runtime/generated/content/content_app_config_client_dto.g.dart",
	"lib/cloud/runtime/generated/content/content_api_metadata.g.dart",
	"lib/cloud/runtime/generated/content/article_detail_wire_keys.g.dart",
	"lib/cloud/runtime/generated/content/content_metadata.g.dart",
	"lib/cloud/runtime/generated/content/content_dtos.dart",
	"lib/cloud/runtime/generated/content/content_post_immersive_wire_keys.g.dart",
	"lib/cloud/runtime/generated/content/content_request_page_ids.g.dart",
	"lib/cloud/runtime/generated/content/post_read_presentation.g.dart",
	"lib/cloud/runtime/generated/content/post_read_surface_id.g.dart",
	"lib/cloud/runtime/generated/content/report_create_request_wire.g.dart",
	"lib/cloud/runtime/generated/entity/entity_request_page_ids.g.dart",
	"lib/cloud/runtime/generated/entity/entity_api_metadata.g.dart",
	"lib/cloud/runtime/generated/entity/homepage_models.dart",
	"lib/cloud/runtime/generated/entity/homepage_ui_config.g.dart",
	"lib/cloud/runtime/generated/integration/integration_api_metadata.g.dart",
	"lib/cloud/runtime/generated/integration/integration_location_errors.g.dart",
	"lib/cloud/runtime/generated/integration/integration_location_metadata.g.dart",
	"lib/cloud/runtime/generated/integration/location_poi_dto.g.dart",
	"lib/cloud/runtime/generated/integration/integration_request_page_ids.g.dart",
	"lib/cloud/runtime/generated/link_templates.g.dart",
	"lib/cloud/runtime/generated/notification/notification_errors.g.dart",
	"lib/cloud/runtime/generated/notification/notification_api_metadata.g.dart",
	"lib/cloud/runtime/generated/notification/notification_request_page_ids.g.dart",
	"lib/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart",
	"lib/cloud/runtime/generated/ops/ops_api_metadata.g.dart",
	"lib/cloud/runtime/generated/ops/ops_event_record_errors.g.dart",
	"lib/cloud/runtime/generated/ops/ops_request_page_ids.g.dart",
	"lib/cloud/runtime/generated/realtime/realtime_api_metadata.g.dart",
	"lib/cloud/runtime/generated/realtime/realtime_request_page_ids.g.dart",
	"lib/cloud/runtime/generated/recommendation/feed_realtime_patch.g.dart",
	"lib/cloud/runtime/generated/recommendation/impact_help_type_metadata.g.dart",
	"lib/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart",
	"lib/cloud/runtime/generated/recommendation/recommendation_api_metadata.g.dart",
	"lib/cloud/runtime/generated/recommendation/recommendation_request_page_ids.g.dart",
	"lib/cloud/runtime/generated/rtc/rtc_api_metadata.g.dart",
	"lib/cloud/runtime/generated/rtc/rtc_request_page_ids.g.dart",
	"lib/cloud/runtime/generated/rtc/rtc_signal_payloads.g.dart",
	"lib/cloud/runtime/generated/search/search_api_metadata.g.dart",
	"lib/cloud/runtime/generated/search/search_contract.g.dart",
	"lib/cloud/runtime/generated/search/search_errors.g.dart",
	"lib/cloud/runtime/generated/search/search_request_page_ids.g.dart",
	"lib/cloud/runtime/generated/search/search_registry.g.dart",
	"lib/cloud/runtime/generated/tag/tag_api_metadata.g.dart",
	"lib/cloud/runtime/generated/tag/tag_errors.g.dart",
	"lib/cloud/runtime/generated/tag/tag_request_page_ids.g.dart",
	"lib/cloud/runtime/generated/travel/travel_api_metadata.g.dart",
	"lib/cloud/runtime/generated/travel/travel_request_page_ids.g.dart",
	"lib/cloud/runtime/generated/user/user_api_metadata.g.dart",
	"lib/cloud/runtime/generated/user/user_errors.g.dart",
	"lib/cloud/runtime/generated/user/user_request_page_ids.g.dart",
	"packages/quwoquan_cloud_contracts/lib/src/rtc/call_session_dtos.g.dart",
}

const appOnlyEmitter = "app-only-emitter"

type generatedOutput struct {
	Path                string `json:"path"`
	Owner               string `json:"owner"`
	Generator           string `json:"generator"`
	ContractGraphSHA256 string `json:"contractGraphSha256"`
	SHA256              string `json:"sha256"`
	Bytes               int    `json:"bytes"`
}

type appGeneratedManifest struct {
	Generator           string            `json:"generator"`
	ContractGraphSHA256 string            `json:"contractGraphSha256"`
	Outputs             []generatedOutput `json:"outputs"`
}

var (
	generatedManifestAppRoot string
	generatedManifestGraph   string
	generatedManifestOutputs = map[string]generatedOutput{}
)

func beginGeneratedManifest(appDir, graphSHA256 string) {
	root, err := filepath.Abs(appDir)
	if err != nil {
		exitErr(fmt.Errorf("resolve App root for generated manifest: %w", err))
	}
	generatedManifestAppRoot = filepath.Clean(root)
	generatedManifestGraph = graphSHA256
	generatedManifestOutputs = map[string]generatedOutput{}
}

func recordGeneratedFile(path string, content []byte) {
	if generatedManifestAppRoot == "" {
		return
	}
	absolute, err := filepath.Abs(path)
	if err != nil {
		exitErr(fmt.Errorf("resolve generated output %s: %w", path, err))
	}
	relative, err := filepath.Rel(
		generatedManifestAppRoot,
		filepath.Clean(absolute),
	)
	if err != nil ||
		relative == ".." ||
		strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		exitErr(fmt.Errorf(
			"App-only emitter attempted to write outside App root: %s",
			path,
		))
	}
	sum := sha256.Sum256(content)
	normalized := filepath.ToSlash(relative)
	generatedManifestOutputs[normalized] = generatedOutput{
		Path:                normalized,
		Owner:               "app-only-emitter",
		Generator:           appOnlyEmitter,
		ContractGraphSHA256: generatedManifestGraph,
		SHA256:              hex.EncodeToString(sum[:]),
		Bytes:               len(content),
	}
}

func removeUntrackedGeneratedOutputs() error {
	if generatedManifestAppRoot == "" {
		return fmt.Errorf("App generated manifest root is not initialized")
	}
	roots := make(
		[]string,
		0,
		len(appGeneratedOutputRoots)+
			len(appGeneratedExactOutputs)+
			len(appRetiredGeneratedOutputRoots)+
			len(appRetiredGeneratedExactOutputs),
	)
	roots = append(roots, appGeneratedOutputRoots...)
	roots = append(roots, appGeneratedExactOutputs...)
	roots = append(roots, appRetiredGeneratedOutputRoots...)
	roots = append(roots, appRetiredGeneratedExactOutputs...)
	for _, relativeRoot := range roots {
		root := filepath.Join(generatedManifestAppRoot, filepath.FromSlash(relativeRoot))
		if _, err := os.Stat(root); err != nil {
			if os.IsNotExist(err) {
				continue
			}
			return fmt.Errorf("inspect App generated root %s: %w", root, err)
		}
		err := filepath.WalkDir(root, func(path string, entry os.DirEntry, walkErr error) error {
			if walkErr != nil {
				return walkErr
			}
			if entry.IsDir() || filepath.Ext(path) != ".dart" {
				return nil
			}
			relative, err := filepath.Rel(generatedManifestAppRoot, path)
			if err != nil {
				return err
			}
			normalized := filepath.ToSlash(relative)
			if _, current := generatedManifestOutputs[normalized]; current {
				return nil
			}
			file, err := os.Open(path)
			if err != nil {
				return err
			}
			header := make([]byte, 300)
			count, readErr := file.Read(header)
			closeErr := file.Close()
			if readErr != nil && count == 0 {
				return readErr
			}
			if closeErr != nil {
				return closeErr
			}
			header = header[:count]
			normalizedHeader := strings.ToLower(string(header))
			if !strings.Contains(normalizedHeader, "generated") ||
				!strings.Contains(normalizedHeader, "do not edit") {
				return nil
			}
			if err := os.Remove(path); err != nil {
				return fmt.Errorf("remove untracked generated output %s: %w", path, err)
			}
			fmt.Printf("retired generated: %s\n", path)
			return nil
		})
		if err != nil {
			return fmt.Errorf("scan App generated root %s: %w", root, err)
		}
	}
	return nil
}

func writeGeneratedManifest(path string) error {
	outputs := make([]generatedOutput, 0, len(generatedManifestOutputs))
	for _, output := range generatedManifestOutputs {
		outputs = append(outputs, output)
	}
	sort.Slice(outputs, func(i, j int) bool {
		return outputs[i].Path < outputs[j].Path
	})
	manifest := appGeneratedManifest{
		Generator:           appOnlyEmitter,
		ContractGraphSHA256: generatedManifestGraph,
		Outputs:             outputs,
	}
	data, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return fmt.Errorf("encode App generated manifest: %w", err)
	}
	data = append(data, '\n')
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return fmt.Errorf("create App generated manifest directory: %w", err)
	}
	if err := os.WriteFile(path, data, 0644); err != nil {
		return fmt.Errorf("write App generated manifest: %w", err)
	}
	fmt.Printf("generated manifest: %s\n", path)
	return nil
}
