package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/graph"
)

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestShellNavigationMetadataModeGeneratesAndChecksOnlyShellOutputs(
	t *testing.T,
) {
	metadataDir := t.TempDir()
	appDir := t.TempDir()
	manifestPath := filepath.Join(
		appDir,
		"tool",
		"shell_navigation_codegen",
		"generated_manifest.json",
	)
	setShellNavigationSourceForTest(t, metadataDir)

	documents, err := readShellNavigationDocuments(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	if err := validateShellNavigationDocuments(documents); err != nil {
		t.Fatal(err)
	}
	artifacts := renderShellNavigationArtifacts(appDir, documents)
	manifest, err := buildShellNavigationManifest(artifacts)
	if err != nil {
		t.Fatal(err)
	}
	if err := writeShellNavigationArtifacts(
		appDir,
		manifestPath,
		artifacts,
		manifest,
	); err != nil {
		t.Fatal(err)
	}
	if err := checkShellNavigationArtifacts(
		appDir,
		manifestPath,
		artifacts,
		manifest,
	); err != nil {
		t.Fatal(err)
	}

	routeOutput, err := os.ReadFile(
		runtimeNavigationOutputPath(appDir, "app_route_paths.g.dart"),
	)
	if err != nil {
		t.Fatal(err)
	}
	for _, token := range []string{
		"AppRoutePaths",
		"gatheringCreate",
		"gatheringDetail",
		"gatheringBoard",
	} {
		if !strings.Contains(string(routeOutput), token) {
			t.Fatalf("generated route output missing %q", token)
		}
	}
	surfaceOutput, err := os.ReadFile(
		runtimeNavigationOutputPath(appDir, "app_ui_surfaces.g.dart"),
	)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(surfaceOutput), "AppUiSurfaces") {
		t.Fatal("generated surface output misses AppUiSurfaces")
	}
	pageOutput, err := os.ReadFile(
		runtimeNavigationOutputPath(appDir, "app_pages.g.dart"),
	)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(pageOutput), "AppPages") {
		t.Fatal("generated page output misses AppPages")
	}
	combinedOutput := strings.Join([]string{
		string(routeOutput),
		string(surfaceOutput),
		string(pageOutput),
	}, "\n")
	for _, retired := range []string{
		"travelTrips",
		"travelTemplates",
		"travelTimeline",
		"travelMap",
		"travelShare",
		"travel_trips",
		"travel_templates",
		"travel_timeline",
		"travel_map",
		"travel_share",
	} {
		if strings.Contains(combinedOutput, retired) {
			t.Fatalf("generated shell navigation retains retired Travel ID %q", retired)
		}
	}

	manifestPayload, err := os.ReadFile(manifestPath)
	if err != nil {
		t.Fatal(err)
	}
	for _, forbidden := range []string{
		"contractGraph",
		"operation_contract",
		"cloud_codegen",
	} {
		if strings.Contains(string(manifestPayload), forbidden) {
			t.Fatalf(
				"shell navigation manifest contains cloud handoff field %q",
				forbidden,
			)
		}
	}
}

func TestShellNavigationAllowsSharedPageNameAcrossDistinctRoutes(t *testing.T) {
	metadataDir := t.TempDir()
	setShellNavigationSourceForTest(t, metadataDir)
	documents, err := readShellNavigationDocuments(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	documents.pages.Pages[1].PageName = documents.pages.Pages[0].PageName
	if err := validateShellNavigationDocuments(documents); err != nil {
		t.Fatalf("shared page_name across distinct routes must remain valid: %v", err)
	}

	documents.pages.Pages[1].RouteID = documents.pages.Pages[0].RouteID
	err = validateShellNavigationDocuments(documents)
	if err == nil || !strings.Contains(err.Error(), "duplicate shell navigation page route_id") {
		t.Fatalf("duplicate route_id error = %v", err)
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestShellNavigationCheckFailsForStaleAndOrphanOutputs(t *testing.T) {
	metadataDir := t.TempDir()
	appDir := t.TempDir()
	manifestPath := filepath.Join(appDir, "shell_manifest.json")
	setShellNavigationSourceForTest(t, metadataDir)
	documents, err := readShellNavigationDocuments(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	artifacts := renderShellNavigationArtifacts(appDir, documents)
	manifest, err := buildShellNavigationManifest(artifacts)
	if err != nil {
		t.Fatal(err)
	}
	if err := writeShellNavigationArtifacts(
		appDir,
		manifestPath,
		artifacts,
		manifest,
	); err != nil {
		t.Fatal(err)
	}

	stalePath := runtimeNavigationOutputPath(appDir, "app_pages.g.dart")
	if err := os.WriteFile(
		stalePath,
		[]byte("// Code generated. DO NOT EDIT.\n// stale\n"),
		0o644,
	); err != nil {
		t.Fatal(err)
	}
	err = checkShellNavigationArtifacts(
		appDir,
		manifestPath,
		artifacts,
		manifest,
	)
	if err == nil || !strings.Contains(err.Error(), "is stale") {
		t.Fatalf("stale output check error = %v", err)
	}
	if err := os.WriteFile(stalePath, artifacts[0].content, 0o644); err != nil {
		t.Fatal(err)
	}

	orphanPath := runtimeNavigationOutputPath(appDir, "orphan.g.dart")
	if err := os.WriteFile(
		orphanPath,
		[]byte("// Code generated. DO NOT EDIT.\n"),
		0o644,
	); err != nil {
		t.Fatal(err)
	}
	err = checkShellNavigationArtifacts(
		appDir,
		manifestPath,
		artifacts,
		manifest,
	)
	if err == nil || !strings.Contains(err.Error(), "orphan") {
		t.Fatalf("orphan output check error = %v", err)
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-codegen/template-engine-and-metadata-reader/spec.md#gwt-001
func TestShellNavigationModeBranchesBeforeCloudContractHandoff(t *testing.T) {
	source, err := os.ReadFile("main.go")
	if err != nil {
		t.Fatal(err)
	}
	text := string(source)
	modeIndex := strings.Index(text, "if shellNavigationMetadataOnly {")
	handoffIndex := strings.Index(text, "initializeContractGraphBundle(")
	if modeIndex < 0 || handoffIndex < 0 || modeIndex >= handoffIndex {
		t.Fatal(
			"shell navigation metadata-only mode must return before cloud ContractGraph handoff initialization",
		)
	}
	branch := text[modeIndex:handoffIndex]
	for _, forbidden := range []string{
		"contractGraphLockPath",
		"generatedManifestPath",
		"activeContractLock",
	} {
		if strings.Contains(branch, forbidden) {
			t.Fatalf(
				"shell navigation metadata-only branch references %s",
				forbidden,
			)
		}
	}
}

func setShellNavigationSourceForTest(t *testing.T, metadataDir string) {
	t.Helper()
	documents := map[string]any{
		"_shared/app_routes.yaml": map[string]any{
			"routes": []map[string]any{
				{"id": "gatheringCreate", "path": "/gatherings/create"},
				{"id": "gatheringDetail", "path": "/gatherings/{id}"},
				{"id": "gatheringBoard", "path": "/chat/{id}/board"},
			},
		},
		"_shared/app_pages.yaml": map[string]any{
			"pages": []map[string]any{
				{
					"page_name":           "gathering_create",
					"route_id":            "gatheringCreate",
					"collect_page_access": true,
				},
				{
					"page_name":           "gathering_detail",
					"route_id":            "gatheringDetail",
					"collect_page_access": true,
				},
				{
					"page_name":           "gathering_board",
					"route_id":            "gatheringBoard",
					"collect_page_access": true,
				},
			},
			"internal_pages": []map[string]any{
				{
					"page_name":           "shell_modal",
					"internal_id":         "shellModal",
					"location":            "page_internal_shell_modal",
					"collect_page_access": true,
				},
			},
			"fallback_contexts": []string{"unknown"},
		},
		"_shared/ui_surfaces.yaml": map[string]any{
			"surfaces": []map[string]any{
				{
					"id":            "gatheringCreate",
					"owner":         "circle",
					"route_id":      "gatheringCreate",
					"path_template": "/gatherings/create",
					"description":   "Gathering create",
					"operation_ids": []string{"CreateGatheringDraft"},
				},
				{
					"id":            "gatheringDetail",
					"owner":         "circle",
					"route_id":      "gatheringDetail",
					"path_template": "/gatherings/{id}",
					"description":   "Gathering detail",
					"operation_ids": []string{"GetGathering"},
				},
				{
					"id":            "gatheringBoard",
					"owner":         "chat",
					"route_id":      "gatheringBoard",
					"path_template": "/chat/{id}/board",
					"description":   "Gathering board",
					"operation_ids": []string{"GetGatheringChatBoard"},
				},
			},
		},
		"_shared/link_templates.yaml": map[string]any{
			"version": 1,
			"runtime_origin_binding": map[string]any{
				"dart_define_key":   "PUBLIC_WEB_BASE_URL",
				"remote_config_key": "public_web_base_url",
			},
			"entities": map[string]any{},
			"citation_destinations": map[string]any{
				"internal": []any{},
				"external": map[string]any{
					"allowed_schemes": []string{"https"},
				},
			},
		},
	}
	sourceDocuments := make(
		[]ast.SourceDocument,
		0,
		len(shellNavigationMetadataPaths),
	)
	for _, path := range shellNavigationMetadataPaths {
		content, err := json.Marshal(documents[path])
		if err != nil {
			t.Fatal(err)
		}
		sourceDocuments = append(sourceDocuments, ast.SourceDocument{
			Path:      path,
			MediaType: "application/json",
			Content:   content,
		})
	}
	previousSource := activeMetadataSource
	previousRoot := activeMetadataRoot
	activeMetadataSource = contractcodegen.NewSourceFromGraph(
		metadataDir,
		&graph.ContractGraph{Documents: sourceDocuments},
	)
	activeMetadataRoot = metadataDir
	t.Cleanup(func() {
		activeMetadataSource = previousSource
		activeMetadataRoot = previousRoot
	})
}
