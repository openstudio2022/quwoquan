package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestDirectNonAssistantGeneratedTargetsHaveSingleCanonicalOwners(
	t *testing.T,
) {
	appDir := t.TempDir()
	navigationOutputs := []string{
		"app_pages.g.dart",
		"app_route_paths.g.dart",
		"app_ui_surfaces.g.dart",
		"page_access_internal_routes.g.dart",
		"link_templates.g.dart",
	}
	for _, fileName := range navigationOutputs {
		want := filepath.Join(
			appDir,
			"lib/runtime/shell/navigation/generated",
			fileName,
		)
		if got := runtimeNavigationOutputPath(appDir, fileName); got != want {
			t.Fatalf("navigation target %s = %q, want %q", fileName, got, want)
		}
	}

	errorOutputs := map[string]string{
		"assistant":    "assistant_errors.g.dart",
		"chat":         "chat_errors.g.dart",
		"circle":       "circle_errors.g.dart",
		"content":      "content_errors.g.dart",
		"entity":       "entity_errors.g.dart",
		"integration":  "integration_location_errors.g.dart",
		"notification": "notification_errors.g.dart",
		"ops":          "ops_event_record_errors.g.dart",
		"rtc":          "rtc_errors.g.dart",
		"search":       "search_errors.g.dart",
		"tag":          "tag_errors.g.dart",
		"user":         "user_errors.g.dart",
	}
	for domain, fileName := range errorOutputs {
		want := filepath.Join(
			appDir,
			"lib/runtime/errors/generated",
			domain,
			fileName,
		)
		if got := runtimeErrorOutputPath(appDir, domain, fileName); got != want {
			t.Fatalf("%s target = %q, want %q", domain, got, want)
		}
	}
	circleMembership := filepath.Join(
		appDir,
		"lib/runtime/errors/generated/circle/circle_membership_errors.g.dart",
	)
	if got := runtimeErrorOutputPath(
		appDir,
		"circle",
		"circle_membership_errors.g.dart",
	); got != circleMembership {
		t.Fatalf("circle membership target = %q, want %q", got, circleMembership)
	}
	gatheringPlan := filepath.Join(
		appDir,
		"lib/runtime/errors/generated/circle/gathering_plan_errors.g.dart",
	)
	if got := runtimeErrorOutputPath(
		appDir,
		"circle",
		"gathering_plan_errors.g.dart",
	); got != gatheringPlan {
		t.Fatalf("gathering plan target = %q, want %q", got, gatheringPlan)
	}

	for _, domain := range []string{
		"assistant",
		"chat",
		"circle",
		"content",
		"entity",
		"integration",
		"notification",
		"ops",
		"realtime",
		"recommendation",
		"rtc",
		"search",
		"tag",
		"travel",
		"user",
	} {
		fileName := domain + "_request_page_ids.g.dart"
		want := filepath.Join(
			appDir,
			"lib/runtime/transport/generated",
			domain,
			fileName,
		)
		if got := runtimeTransportOutputPath(appDir, domain, fileName); got != want {
			t.Fatalf("transport target %s = %q, want %q", domain, got, want)
		}
	}

	telemetry := filepath.Join(
		appDir,
		"lib/runtime/observability/generated/app_telemetry_catalog.g.dart",
	)
	if got := runtimeObservabilityOutputPath(
		appDir,
		"app_telemetry_catalog.g.dart",
	); got != telemetry {
		t.Fatalf("telemetry target = %q, want %q", got, telemetry)
	}

	canonicalOutputs := map[string]struct {
		got  string
		want string
	}{
		"cloud api defaults": {
			got: runtimeTransportSharedOutputPath(
				appDir,
				"cloud_api_defaults.g.dart",
			),
			want: filepath.Join(
				appDir,
				"lib/runtime/transport/generated/cloud_api_defaults.g.dart",
			),
		},
		"content post wire keys": {
			got: contentPostAdaptersOutputPath(
				appDir,
				"article_detail_wire_keys.g.dart",
			),
			want: filepath.Join(
				appDir,
				"lib/service/content_service/content/post/adapters/generated/"+
					"article_detail_wire_keys.g.dart",
			),
		},
		"content image variant policy": {
			got: contentMediaAssetApplicationOutputPath(
				appDir,
				"content_image_variant_policy.g.dart",
			),
			want: filepath.Join(
				appDir,
				"lib/service/content_service/media/media_asset/application/generated/"+
					"content_image_variant_policy.g.dart",
			),
		},
		"content media upload policy": {
			got: contentMediaUploadSessionApplicationOutputPath(
				appDir,
				"content_media_upload_policy.g.dart",
			),
			want: filepath.Join(
				appDir,
				"lib/service/content_service/media/media_upload_session/application/generated/"+
					"content_media_upload_policy.g.dart",
			),
		},
		"content publication policy": {
			got: contentPostDomainOutputPath(
				appDir,
				"content_publication_policy.g.dart",
			),
			want: filepath.Join(
				appDir,
				"lib/service/content_service/content/post/domain/generated/"+
					"content_publication_policy.g.dart",
			),
		},
		"content feed category policy": {
			got: contentPostApplicationOutputPath(
				appDir,
				"content_feed_category_policy.g.dart",
			),
			want: filepath.Join(
				appDir,
				"lib/service/content_service/content/post/application/generated/"+
					"content_feed_category_policy.g.dart",
			),
		},
		"post read surface": {
			got: contentPostPresentationOutputPath(
				appDir,
				"post_read_surface_id.g.dart",
			),
			want: filepath.Join(
				appDir,
				"lib/service/content_service/content/post/presentation/generated/"+
					"post_read_surface_id.g.dart",
			),
		},
		"circle UI config": {
			got: circlePresentationOutputPath(appDir, "circle_ui_config.g.dart"),
			want: filepath.Join(
				appDir,
				"lib/service/circle_service/circle_management/circle/presentation/generated/"+
					"circle_ui_config.g.dart",
			),
		},
		"homepage UI config": {
			got: entityHomepagePresentationOutputPath(
				appDir,
				"homepage_ui_config.g.dart",
			),
			want: filepath.Join(
				appDir,
				"lib/service/entity_service/entity_homepage/homepage/application/public/generated/"+
					"homepage_ui_config.g.dart",
			),
		},
		"user profile UI config": {
			got: userAccountPresentationOutputPath(
				appDir,
				"user_profile_ui_config.g.dart",
			),
			want: filepath.Join(
				appDir,
				"lib/service/user_service/account/user_account/application/public/generated/"+
					"user_profile_ui_config.g.dart",
			),
		},
		"recommendation impact help metadata": {
			got: recommendationFeatureProfilePresentationOutputPath(
				appDir,
				"impact_help_type_metadata.g.dart",
			),
			want: filepath.Join(
				appDir,
				"lib/service/recommendation_service/recommendation/"+
					"recommendation_feature_profile_view/presentation/generated/"+
					"impact_help_type_metadata.g.dart",
			),
		},
		"intersection client policy": {
			got: recommendationFeatureProfileApplicationOutputPath(
				appDir,
				"intersection_client_policy.g.dart",
			),
			want: filepath.Join(
				appDir,
				"lib/service/recommendation_service/recommendation/"+
					"recommendation_feature_profile_view/application/generated/"+
					"intersection_client_policy.g.dart",
			),
		},
		"intersection display metadata": {
			got: recommendationFeatureProfilePresentationOutputPath(
				appDir,
				"intersection_display_metadata.g.dart",
			),
			want: filepath.Join(
				appDir,
				"lib/service/recommendation_service/recommendation/"+
					"recommendation_feature_profile_view/presentation/generated/"+
					"intersection_display_metadata.g.dart",
			),
		},
	}
	for name, output := range canonicalOutputs {
		if output.got != output.want {
			t.Fatalf("%s target = %q, want %q", name, output.got, output.want)
		}
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestMainEmitsRuntimeArtifactsOnlyThroughCanonicalTargetHelpers(t *testing.T) {
	sourceFiles := []string{
		"content_metadata_split_codegen.go",
		"impact_help_type_metadata_codegen.go",
		"main.go",
		"post_read_presentation_codegen.go",
		"shell_navigation_codegen.go",
		"ui_config_entity_circle.go",
	}
	var combined strings.Builder
	for _, sourceFile := range sourceFiles {
		source, err := os.ReadFile(sourceFile)
		if err != nil {
			t.Fatal(err)
		}
		combined.Write(source)
		combined.WriteByte('\n')
	}
	text := combined.String()
	required := []string{
		`runtimeNavigationOutputPath(appDir, name)`,
		`runtimeTransportOutputPath(`,
		`runtimeErrorOutputPath(appDir, "assistant", "assistant_errors.g.dart")`,
		`runtimeErrorOutputPath(appDir, "chat", "chat_errors.g.dart")`,
		`runtimeErrorOutputPath(appDir, "circle", "circle_errors.g.dart")`,
		`runtimeErrorOutputPath(appDir, "circle", "circle_membership_errors.g.dart")`,
		`runtimeErrorOutputPath(appDir, "circle", "gathering_plan_errors.g.dart")`,
		`runtimeErrorOutputPath(appDir, "content", "content_errors.g.dart")`,
		`runtimeErrorOutputPath(appDir, "entity", "entity_errors.g.dart")`,
		`runtimeErrorOutputPath(appDir, "integration", "integration_location_errors.g.dart")`,
		`runtimeErrorOutputPath(appDir, "notification", "notification_errors.g.dart")`,
		`runtimeErrorOutputPath(appDir, "ops", "ops_event_record_errors.g.dart")`,
		`runtimeErrorOutputPath(appDir, "rtc", "rtc_errors.g.dart")`,
		`runtimeErrorOutputPath(appDir, "search", "search_errors.g.dart")`,
		`runtimeErrorOutputPath(appDir, "tag", "tag_errors.g.dart")`,
		`runtimeErrorOutputPath(appDir, "user", "user_errors.g.dart")`,
		`runtimeObservabilityOutputPath(appDir, "app_telemetry_catalog.g.dart")`,
		`contentMediaAssetApplicationOutputPath(`,
		`contentMediaUploadSessionApplicationOutputPath(`,
		`contentPostApplicationOutputPath(`,
		`contentPostDomainOutputPath(`,
		`contentPostPresentationOutputPath(`,
		`circlePresentationOutputPath(`,
		`entityHomepagePresentationOutputPath(`,
		`recommendationFeatureProfilePresentationOutputPath(`,
		`userAccountPresentationOutputPath(`,
	}
	for _, call := range required {
		if !strings.Contains(text, call) {
			t.Fatalf("main.go missing canonical generated target call %s", call)
		}
	}
	for _, output := range []string{
		"app_route_paths.g.dart",
		"app_ui_surfaces.g.dart",
		"app_pages.g.dart",
		"link_templates.g.dart",
		"page_access_internal_routes.g.dart",
	} {
		if !strings.Contains(text, `"`+output+`"`) {
			t.Fatalf("shell generator missing canonical output %s", output)
		}
	}
	forbidden := []string{
		`"app", "navigation", "generated"`,
		`"application", "content", "media", "generated"`,
		`"cloud", "assistant", "generated", "assistant_errors.g.dart"`,
		`"cloud", "chat", "generated", "chat_errors.g.dart"`,
		`"cloud", "circle", "generated", "circle_errors.g.dart"`,
		`"cloud", "circle", "generated", "circle_membership_errors.g.dart"`,
		`"cloud", "content", "generated", "content_errors.g.dart"`,
		`"cloud", "entity", "generated", "entity_errors.g.dart"`,
		`"cloud", "rtc", "generated", "rtc_errors.g.dart"`,
		`"generated", "integration", "integration_location_errors.g.dart"`,
		`"generated", "notification", "notification_errors.g.dart"`,
		`"generated", "ops", "app_telemetry_catalog.g.dart"`,
		`"generated", "ops", "ops_event_record_errors.g.dart"`,
		`"generated", "search", "search_errors.g.dart"`,
		`"generated", "tag", "tag_errors.g.dart"`,
		`"generated", "user", "user_errors.g.dart"`,
		`"generated", domain, fmt.Sprintf("%s_request_page_ids.g.dart", domain)`,
		`"cloud", "content", "generated", "content_publication_policy.g.dart"`,
		`"cloud", "user", "generated", "user_profile_ui_config.g.dart"`,
		`"generated", "content", "post_read_surface_id.g.dart"`,
		`"generated", "content", "post_read_presentation.g.dart"`,
		`"generated", "entity", "homepage_ui_config.g.dart"`,
		`"generated", "circle", "circle_ui_config.g.dart"`,
		`"generated", "link_templates.g.dart"`,
	}
	for _, oldTarget := range forbidden {
		if strings.Contains(text, oldTarget) {
			t.Fatalf("main.go still emits retired generated target %s", oldTarget)
		}
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestZeroConsumerMixedOutputsHaveNoEmitterSource(t *testing.T) {
	sources := map[string][]string{
		"main.go": {
			"content_metadata.g.dart",
			"search_contract.g.dart",
			"search_registry.g.dart",
		},
		"intersection_kind_metadata_codegen.go": {
			"intersection_kind_metadata.g.dart",
		},
		"post_read_presentation_codegen.go": {
			"content_post_immersive_wire_keys.g.dart",
		},
	}
	for sourcePath, retiredOutputs := range sources {
		source, err := os.ReadFile(sourcePath)
		if err != nil {
			t.Fatal(err)
		}
		for _, retiredOutput := range retiredOutputs {
			if strings.Contains(string(source), retiredOutput) {
				t.Fatalf("%s still emits retired output %s", sourcePath, retiredOutput)
			}
		}
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestAssistantGenerationHasNoImperativeLegacyOutputCleanup(t *testing.T) {
	source, err := os.ReadFile("assistant_codegen.go")
	if err != nil {
		t.Fatal(err)
	}
	text := string(source)
	for _, retired := range []string{
		"lib/assistant/generated/contracts",
		"session_state_decision.g.dart",
		"os.Remove(",
	} {
		if strings.Contains(text, retired) {
			t.Fatalf(
				"Assistant generator retained imperative legacy cleanup %q; stale outputs must be removed by the generated manifest retirement roots",
				retired,
			)
		}
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestGeneratedManifestSeparatesCanonicalAndRetirementRoots(t *testing.T) {
	active := make(map[string]struct{}, len(appGeneratedOutputRoots))
	for _, root := range appGeneratedOutputRoots {
		active[root] = struct{}{}
	}
	for _, root := range []string{
		"lib/service/circle_service/circle_management/circle/presentation/generated",
		"lib/service/content_service/content/post/adapters/generated",
		"lib/service/content_service/content/post/application/generated",
		"lib/service/content_service/content/post/domain/generated",
		"lib/service/content_service/content/post/presentation/generated",
		"lib/service/content_service/media/media_asset/application/generated",
		"lib/service/content_service/media/media_upload_session/application/generated",
		"lib/service/entity_service/entity_homepage/homepage/application/public/generated",
		"lib/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/generated",
		"lib/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/generated",
		"lib/runtime/errors/generated",
		"lib/runtime/transport/generated",
		"lib/service/search_service/search/search_index_view/application/generated",
		"lib/service/search_service/search/search_index_view/presentation/generated",
		"lib/service/user_service/account/user_account/application/public/generated",
	} {
		if _, ok := active[root]; !ok {
			t.Fatalf("canonical generated root is not active: %s", root)
		}
	}
	for _, mixedRoot := range []string{
		"lib/cloud/content/generated",
		"lib/cloud/runtime/generated",
		"lib/runtime/shell/navigation/generated",
		"packages/quwoquan_cloud_contracts/lib/src/rtc",
	} {
		if _, ok := active[mixedRoot]; ok {
			t.Fatalf("mixed-owner generated root must not be active: %s", mixedRoot)
		}
	}
	retiredRoots := make(
		map[string]struct{},
		len(appRetiredGeneratedOutputRoots),
	)
	for _, retired := range appRetiredGeneratedOutputRoots {
		retiredRoots[retired] = struct{}{}
		if _, ok := active[retired]; ok {
			t.Fatalf("retired generated root is still active: %s", retired)
		}
	}
	for _, oldRoot := range []string{
		"lib/app/navigation/generated",
		"lib/application/content/media/generated",
		"lib/cloud/assistant/generated",
		"lib/cloud/chat/generated",
		"lib/cloud/circle/generated",
		"lib/cloud/entity/generated",
		"lib/cloud/rtc/generated",
		"lib/cloud/user/generated",
	} {
		if _, ok := retiredRoots[oldRoot]; !ok {
			t.Fatalf("retired direct generated root is not scanned: %s", oldRoot)
		}
	}
	retiredExact := make(
		map[string]struct{},
		len(appRetiredGeneratedExactOutputs),
	)
	for _, path := range appRetiredGeneratedExactOutputs {
		retiredExact[path] = struct{}{}
	}
	expectedRetiredExact := []string{
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
		"lib/cloud/runtime/generated/auth/auth_policy.g.dart",
		"lib/cloud/runtime/generated/cloud_api_defaults.g.dart",
		"lib/cloud/runtime/generated/circle/circle_category_tab_config_dto.dart",
		"lib/cloud/runtime/generated/circle/circle_category_tab_defaults.dart",
		"lib/cloud/runtime/generated/circle/circle_category_tab_order.dart",
		"lib/cloud/runtime/generated/circle/circle_detail_wire_dto.dart",
		"lib/cloud/runtime/generated/circle/circle_dto.dart",
		"lib/cloud/runtime/generated/circle/circle_dtos.dart",
		"lib/cloud/runtime/generated/circle/circle_member_dto.dart",
		"lib/cloud/runtime/generated/circle/circle_member_roster_item_dto.dart",
		"lib/cloud/runtime/generated/circle/circle_section_config_dto.dart",
		"lib/cloud/runtime/generated/circle/circle_ui_config.g.dart",
		"lib/cloud/runtime/generated/content/article_detail_wire_keys.g.dart",
		"lib/cloud/runtime/generated/content/content_app_config_client_dto.g.dart",
		"lib/cloud/runtime/generated/content/content_metadata.g.dart",
		"lib/cloud/runtime/generated/content/content_dtos.dart",
		"lib/cloud/runtime/generated/content/content_post_immersive_wire_keys.g.dart",
		"lib/cloud/runtime/generated/content/post_read_presentation.g.dart",
		"lib/cloud/runtime/generated/content/post_read_surface_id.g.dart",
		"lib/cloud/runtime/generated/content/report_create_request_wire.g.dart",
		"lib/cloud/runtime/generated/entity/homepage_models.dart",
		"lib/cloud/runtime/generated/entity/homepage_ui_config.g.dart",
		"lib/cloud/runtime/generated/integration/integration_location_errors.g.dart",
		"lib/cloud/runtime/generated/integration/integration_location_metadata.g.dart",
		"lib/cloud/runtime/generated/integration/location_poi_dto.g.dart",
		"lib/cloud/runtime/generated/link_templates.g.dart",
		"lib/cloud/runtime/generated/notification/notification_errors.g.dart",
		"lib/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart",
		"lib/cloud/runtime/generated/ops/ops_event_record_errors.g.dart",
		"lib/cloud/runtime/generated/recommendation/feed_realtime_patch.g.dart",
		"lib/cloud/runtime/generated/recommendation/impact_help_type_metadata.g.dart",
		"lib/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart",
		"lib/cloud/runtime/generated/rtc/rtc_signal_payloads.g.dart",
		"lib/cloud/runtime/generated/search/search_contract.g.dart",
		"lib/cloud/runtime/generated/search/search_errors.g.dart",
		"lib/cloud/runtime/generated/search/search_registry.g.dart",
		"lib/cloud/runtime/generated/tag/tag_errors.g.dart",
		"lib/cloud/runtime/generated/user/user_errors.g.dart",
		"packages/quwoquan_cloud_contracts/lib/src/rtc/call_session_dtos.g.dart",
	}
	for _, domain := range []string{
		"assistant",
		"chat",
		"circle",
		"content",
		"entity",
		"integration",
		"notification",
		"ops",
		"realtime",
		"recommendation",
		"rtc",
		"search",
		"tag",
		"travel",
		"user",
	} {
		expectedRetiredExact = append(
			expectedRetiredExact,
			filepath.ToSlash(filepath.Join(
				"lib/cloud/runtime/generated",
				domain,
				domain+"_api_metadata.g.dart",
			)),
			filepath.ToSlash(filepath.Join(
				"lib/cloud/runtime/generated",
				domain,
				domain+"_request_page_ids.g.dart",
			)),
		)
	}
	if got := len(retiredExact); got != len(expectedRetiredExact) {
		t.Fatalf(
			"retired direct exact output count = %d, want %d",
			got,
			len(expectedRetiredExact),
		)
	}
	for _, path := range expectedRetiredExact {
		if _, ok := retiredExact[path]; !ok {
			t.Fatalf("retired direct exact output is not scanned: %s", path)
		}
	}
	exact := make(map[string]struct{}, len(appGeneratedExactOutputs))
	for _, path := range appGeneratedExactOutputs {
		exact[path] = struct{}{}
	}
	expectedExact := []string{
		"lib/runtime/observability/generated/app_telemetry_catalog.g.dart",
		"packages/quwoquan_cloud_contracts/lib/src/rtc/rtc_operation_contracts.g.dart",
	}
	if got := len(exact); got != len(expectedExact) {
		t.Fatalf("active exact output count = %d, want %d", got, len(expectedExact))
	}
	for _, path := range expectedExact {
		if _, ok := exact[path]; !ok {
			t.Fatalf("shared-root generated output is not exact: %s", path)
		}
	}
	if _, ok := active["lib/runtime/observability/generated"]; ok {
		t.Fatal("App emitter must not own the independent observability generator root")
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestFreshGenerationRemovesRetiredRuntimeOutputs(t *testing.T) {
	appDir := t.TempDir()
	beginGeneratedManifestForTest(t, appDir, "canonical-graph")
	retired := filepath.Join(
		appDir,
		"lib/cloud/assistant/generated/assistant_errors.g.dart",
	)
	retiredPostReadPresentation := filepath.Join(
		appDir,
		"lib/cloud/runtime/generated/content/post_read_presentation.g.dart",
	)
	staleTelemetry := filepath.Join(
		appDir,
		"lib/runtime/observability/generated/app_telemetry_catalog.g.dart",
	)
	independentRuntimeLog := filepath.Join(
		appDir,
		"lib/runtime/observability/generated/runtime_log_catalog.g.dart",
	)
	for _, path := range []string{
		retired,
		retiredPostReadPresentation,
		staleTelemetry,
		independentRuntimeLog,
	} {
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(
			path,
			[]byte("// Code generated. DO NOT EDIT.\n"),
			0o644,
		); err != nil {
			t.Fatal(err)
		}
	}
	if err := removeUntrackedGeneratedOutputs(); err != nil {
		t.Fatal(err)
	}
	for _, path := range []string{
		retired,
		retiredPostReadPresentation,
		staleTelemetry,
	} {
		if _, err := os.Stat(path); !os.IsNotExist(err) {
			t.Fatalf("retired runtime output still exists at %s: %v", path, err)
		}
	}
	if _, err := os.Stat(independentRuntimeLog); err != nil {
		t.Fatalf("independent observability output was removed: %v", err)
	}
}
