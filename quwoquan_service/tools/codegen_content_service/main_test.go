package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
	"quwoquan_service/internal/testsupport/contractsview"
)

func contentTestContractSource(t *testing.T) *contractcodegen.Source {
	t.Helper()
	source, err := contractcodegen.NewSource(
		contractsview.Build(t),
		validate.ProfileBaseline,
	)
	if err != nil {
		t.Fatalf("NewSource() error = %v", err)
	}
	return source
}

func TestContentServiceRoutePacketIncludesEveryObjectService(t *testing.T) {
	t.Parallel()

	source := contentTestContractSource(t)
	routes, err := loadServiceRoutes(source, "content-service")
	if err != nil {
		t.Fatalf("loadServiceRoutes() error = %v", err)
	}

	operations := make(map[string]struct{})
	for _, group := range routes {
		for _, route := range group.Routes {
			operations[route.Operation] = struct{}{}
		}
	}
	for _, operation := range []string{
		"SubmitPostPublication",
		"CreateComment",
		"HideComment",
		"RestoreComment",
		"LikePost",
		"InitMediaUpload",
		"GetMediaAssetReference",
		"GetMediaAssetDeliveryReference",
		"CreateOutboundShare",
		"CreateReport",
		"ListMyReports",
		"ListReports",
		"GetReport",
		"BeginReportReview",
		"DismissReport",
		"ResolveReport",
		"GetCurrentPostModerationCase",
		"StageFilterCatalogRelease",
		"ActivateFilterCatalogRelease",
		"RollbackFilterCatalogRelease",
		"GetActiveFilterCatalog",
	} {
		if _, found := operations[operation]; !found {
			t.Errorf("route packet is missing %s", operation)
		}
	}
}

func TestContentServiceRoutePacketUsesCanonicalGetFeedQueryBindings(t *testing.T) {
	t.Parallel()

	source := contentTestContractSource(t)
	routes, err := loadServiceRoutes(source, "content-service")
	if err != nil {
		t.Fatalf("loadServiceRoutes() error = %v", err)
	}

	for _, group := range routes {
		for _, route := range group.Routes {
			if route.Operation != "GetFeed" {
				continue
			}
			for _, name := range []string{
				"identity", "type", "sort", "channelId", "subCategory",
				"cursor", "limit", "feedRequestId",
			} {
				if !containsRequestBinding(route.RequestBindings.Query, name) {
					t.Fatalf(
						"GetFeed canonical query bindings missing %q: %+v",
						name,
						route.RequestBindings.Query,
					)
				}
			}
			if route.Pagination.DefaultItems != 20 ||
				route.Pagination.MaximumItems != 20 {
				t.Fatalf(
					"GetFeed pagination = %+v, want default=20 maximum=20",
					route.Pagination,
				)
			}
			return
		}
	}
	t.Fatal("GetFeed route not found")
}

func TestRequestBodyFieldsDeriveFromRequestEntityAndExcludeCanonicalBindings(
	t *testing.T,
) {
	t.Parallel()

	route := serviceRouteYAML{
		Operation:       "CanonicalCommand",
		RequestEntity:   "CanonicalCommandRequest",
		RequestBodyKind: "object",
		RequestBindings: requestBindingsYAML{
			Path:     []requestBindingYAML{{Name: "objectId", Field: "objectId"}},
			Query:    []requestBindingYAML{{Name: "cursor", Field: "cursor"}},
			Header:   []requestBindingYAML{{Name: "X-Trace", Field: "traceId"}},
			Injected: []requestBindingYAML{{Name: "actor", Field: "actorId"}},
		},
	}
	fields := serviceFieldsYAML{
		Types: map[string]serviceRequestEntityYAML{
			"CanonicalCommandRequest": {
				Fields: []serviceRequestFieldYAML{
					{Name: "objectId"},
					{Name: "cursor"},
					{Name: "traceId"},
					{Name: "actorId"},
					{Name: "title"},
					{Name: "bodyValue", ClientWireName: "body"},
				},
			},
		},
	}

	got, err := deriveRequestBodyFields(route, "post", fields)
	if err != nil {
		t.Fatalf("deriveRequestBodyFields() error = %v", err)
	}
	if strings.Join(got, ",") != "title,body" {
		t.Fatalf("derived body fields = %v, want [title body]", got)
	}
}

func TestContentServicePostBodiesUseCanonicalRequestEntities(t *testing.T) {
	t.Parallel()

	source := contentTestContractSource(t)
	routes, err := loadServiceRoutes(source, "content-service")
	if err != nil {
		t.Fatalf("loadServiceRoutes() error = %v", err)
	}
	wantByOperation := map[string][]string{
		"SubmitPostPublication": {
			"publishIntentId", "localDraftId", "contentType", "location",
		},
		"UpdatePostSettings": {
			"visibility", "primaryHomepageId", "primaryHomepageType",
			"primaryHomepageSnapshot", "assistantUsePolicy",
		},
		"PromotePostToWork": {
			"contentType", "title", "summary", "semanticMentions", "coverUrl",
			"articleMarkdown", "markdownDialect", "articleAssetManifest",
			"articleRenderProfile", "primaryHomepageId", "primaryHomepageType",
			"primaryHomepageSnapshot", "visibility", "assistantUsePolicy",
		},
		"GenerateArticleSummary": {"title", "body"},
	}
	found := map[string]bool{}
	for _, group := range routes {
		for _, route := range group.Routes {
			want, tracked := wantByOperation[route.Operation]
			if !tracked {
				continue
			}
			found[route.Operation] = true
			for _, field := range want {
				if !containsString(route.RequestBodyFields, field) {
					t.Errorf(
						"%s canonical body is missing %s: %v",
						route.Operation,
						field,
						route.RequestBodyFields,
					)
				}
			}
			if containsString(route.RequestBodyFields, "postId") {
				t.Errorf(
					"%s path-bound postId leaked into body: %v",
					route.Operation,
					route.RequestBodyFields,
				)
			}
		}
	}
	for operation := range wantByOperation {
		if !found[operation] {
			t.Errorf("canonical request body route not found: %s", operation)
		}
	}
}

func TestContentServiceContractsDoNotRetainWritableFieldLists(t *testing.T) {
	t.Parallel()

	source := contentTestContractSource(t)
	for _, operationsPath := range source.Paths("content/", "operations.yaml") {
		content, err := source.Content(operationsPath)
		if err != nil {
			t.Fatalf("read %s: %v", operationsPath, err)
		}
		if strings.Contains(string(content), "writable_fields:") {
			t.Errorf("%s retains legacy writable_fields", operationsPath)
		}
	}
}

func containsRequestBinding(values []requestBindingYAML, target string) bool {
	for _, value := range values {
		if value.Name == target {
			return true
		}
	}
	return false
}

func containsString(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

func TestContentServiceReadyOperationsDispatchDirectly(t *testing.T) {
	t.Parallel()

	generated, err := os.ReadFile(filepath.Join(
		"..", "..", "services", "content-service", "internal", "content", "post",
		"adapters", "inbound", "http", "routes.go",
	))
	if err != nil {
		t.Fatalf("read generated routes: %v", err)
	}

	for operation, handler := range map[string]string{
		"BeginReportReview":              "handleBeginReportReview",
		"ActivateFilterCatalogRelease":   "handleActivateFilterCatalogRelease",
		"BindMediaAssetsToComment":       "handleBindMediaAssetsToComment",
		"CreateComment":                  "handleCreateComment",
		"CreateOutboundShare":            "handleCreateOutboundShare",
		"DeleteComment":                  "handleDeleteComment",
		"DismissReport":                  "handleDismissReport",
		"GetActiveFilterCatalog":         "handleGetActiveFilterCatalog",
		"GetMediaImageReprocessRun":      "handleGetMediaImageReprocessRun",
		"GetReport":                      "handleGetReport",
		"GetCurrentPostModerationCase":   "handleGetCurrentPostModerationCase",
		"GetMediaAssetReference":         "handleGetMediaAssetReference",
		"GetMediaAssetDeliveryReference": "handleGetMediaAssetDeliveryReference",
		"HideComment":                    "handleHideComment",
		"ListCommentReplies":             "handleListCommentReplies",
		"ListComments":                   "handleListComments",
		"ListCommentsByAuthor":           "handleListCommentsByAuthor",
		"ListCommentsForPostAuthor":      "handleListCommentsForPostAuthor",
		"ListMyReports":                  "handleListMyReports",
		"ListReports":                    "handleListReports",
		"PinComment":                     "handleSetCommentPinned",
		"PauseMediaImageReprocessRun":    "handlePauseMediaImageReprocessRun",
		"ReactToComment":                 "handleReactToComment",
		"ResolveReport":                  "handleResolveReport",
		"RestoreComment":                 "handleRestoreComment",
		"ResumeMediaImageReprocessRun":   "handleResumeMediaImageReprocessRun",
		"RollbackFilterCatalogRelease":   "handleRollbackFilterCatalogRelease",
		"RollbackMediaImageReprocessRun": "handleRollbackMediaImageReprocessRun",
		"StageFilterCatalogRelease":      "handleStageFilterCatalogRelease",
		"StartMediaImageReprocessRun":    "handleStartMediaImageReprocessRun",
		"SubmitPostPublication":          "handleSubmitPostPublication",
		"UpdatePostSettings":             "handleUpdatePostSettings",
		"PromotePostToWork":              "handlePromotePostToWork",
		"DeletePost":                     "handleDeletePost",
		"UnpinComment":                   "handleSetCommentPinned",
	} {
		block := generatedOperationDispatchBlock(t, string(generated), operation)
		if !strings.Contains(block, "h."+handler+"(") {
			t.Errorf(
				"%s dispatch does not call %s directly:\n%s",
				operation,
				handler,
				block,
			)
		}
		if strings.Contains(block, "handleNotImplemented") {
			t.Errorf(
				"%s dispatch must not route through handleNotImplemented:\n%s",
				operation,
				block,
			)
		}
	}

	for operation, parameters := range map[string][]string{
		"BindMediaAssetsToComment": {"commentId"},
		"CreateComment":            {"postId"},
		"DeleteComment":            {"postId", "commentId"},
		"HideComment":              {"commentId"},
		"ListCommentReplies":       {"postId", "commentId"},
		"ListComments":             {"postId"},
		"PinComment":               {"postId", "commentId"},
		"ReactToComment":           {"commentId"},
		"RestoreComment":           {"commentId"},
		"UnpinComment":             {"postId", "commentId"},
	} {
		block := generatedOperationDispatchBlock(t, string(generated), operation)
		for _, parameter := range parameters {
			want := `r.PathValue("` + parameter + `")`
			if !strings.Contains(block, want) {
				t.Errorf(
					"%s dispatch must consume generated %s path value directly:\n%s",
					operation,
					parameter,
					block,
				)
			}
		}
		if strings.Contains(block, "postIDFromPath") ||
			strings.Contains(block, "commentIDFromPath") {
			t.Errorf(
				"%s dispatch must not re-parse the path after generated routing:\n%s",
				operation,
				block,
			)
		}
	}
}

func TestContentErrorGenerationPreservesStableIdentityAndHTTPMetadata(t *testing.T) {
	t.Parallel()

	source := contentTestContractSource(t)
	outputDir := t.TempDir()
	if err := generateErrorConstants(source, outputDir); err != nil {
		t.Fatalf("generateErrorConstants() error = %v", err)
	}
	generated, err := os.ReadFile(filepath.Join(outputDir, "content", "comment", "errors.go"))
	if err != nil {
		t.Fatalf("read generated errors: %v", err)
	}
	sourceText := string(generated)
	for _, needle := range []string{
		`rterr.ParseCode("CONTENT.USER.comment_pin_forbidden")`,
		`WithMetadata("comment_pin_forbidden", 403)`,
		`WithMetadata("comment_pin_invalid_target", 400)`,
	} {
		if !strings.Contains(sourceText, needle) {
			t.Fatalf("generated errors missing %q", needle)
		}
	}
	profileGenerated, err := os.ReadFile(filepath.Join(
		outputDir,
		"content",
		"profile_interaction_activity_view",
		"errors.go",
	))
	if err != nil {
		t.Fatalf("read generated ProfileInteraction errors: %v", err)
	}
	for _, needle := range []string{
		`rterr.ParseCode("CONTENT.USER.interaction_owner_forbidden")`,
		`rterr.ParseCode("CONTENT.SYSTEM.interaction_read_model_unavailable")`,
		`WithMetadata("interaction_read_model_unavailable", 503)`,
	} {
		if !strings.Contains(string(profileGenerated), needle) {
			t.Fatalf("generated ProfileInteraction errors missing %q", needle)
		}
	}
	readFactGenerated, err := os.ReadFile(filepath.Join(
		outputDir,
		"content",
		"profile_interaction_read_fact",
		"errors.go",
	))
	if err != nil {
		t.Fatalf("read generated ProfileInteractionReadFact errors: %v", err)
	}
	for _, needle := range []string{
		`rterr.ParseCode("CONTENT.USER.profile_interaction_read_fact_owner_forbidden")`,
		`rterr.ParseCode("CONTENT.SYSTEM.profile_interaction_read_fact_target_unavailable")`,
	} {
		if !strings.Contains(string(readFactGenerated), needle) {
			t.Fatalf("generated ProfileInteractionReadFact errors missing %q", needle)
		}
	}
}

func TestContentMediaUploadPolicyGenerationPreservesPerTypeLimits(t *testing.T) {
	t.Parallel()

	source := contentTestContractSource(t)
	outputDir := t.TempDir()
	if err := generateContentMediaUploadPolicy(source, outputDir); err != nil {
		t.Fatalf("generateContentMediaUploadPolicy() error = %v", err)
	}
	generated, err := os.ReadFile(
		filepath.Join(outputDir, "content_media_upload_policy.go"),
	)
	if err != nil {
		t.Fatalf("read generated media upload policy: %v", err)
	}
	sourceText := string(generated)
	for _, needle := range []string{
		"ContentMediaUploadPolicies",
		`"audio": {`,
		"MaxFileSizeBytes: 10485760",
		`"file": {`,
		"MaxFileSizeBytes: 104857600",
		`"audio/wav"`,
		`"video/webm"`,
		`"*/*"`,
	} {
		if !strings.Contains(sourceText, needle) {
			t.Fatalf("generated media upload policy missing %q", needle)
		}
	}
	if strings.Contains(sourceText, "ContentMediaUploadMaxFileSizeBytes int64") {
		t.Fatal("generated policy regressed to one global media size limit")
	}
}

func TestOnboardingInterestCatalogGenerationPreservesDimensionBounds(t *testing.T) {
	t.Parallel()

	source := contentTestContractSource(t)
	outputDir := t.TempDir()
	if err := generateOnboardingInterestCatalog(source, outputDir); err != nil {
		t.Fatalf("generateOnboardingInterestCatalog() error = %v", err)
	}
	generated, err := os.ReadFile(filepath.Join(outputDir, "onboarding_interest_catalog.g.go"))
	if err != nil {
		t.Fatalf("read generated onboarding policy: %v", err)
	}
	sourceText := string(generated)
	for _, needle := range []string{
		"DimensionMinSelections",
		"DimensionMaxSelections",
		`"topic":    4`,
		`"audience": 4`,
	} {
		if !strings.Contains(sourceText, needle) {
			t.Fatalf("generated onboarding catalog policy missing %q", needle)
		}
	}
	if strings.Contains(sourceText, "MaxSelectionsPerDimension") {
		t.Fatal("generated onboarding catalog policy must retain per-dimension bounds")
	}
	// 发布身份是 tag-service 的运行时事实：固化进 content-service 会让发一个
	// 新 tag 发布对全体新用户直接报 invalid_argument。
	if strings.Contains(sourceText, "TaxonomyReleaseID") {
		t.Fatal("generated onboarding catalog policy must not pin a taxonomy release id")
	}
	if strings.Contains(sourceText, "Version") {
		t.Fatal("generated onboarding catalog policy must not carry a version envelope")
	}
}

func generatedOperationDispatchBlock(t *testing.T, generated, operation string) string {
	t.Helper()
	startMarker := fmt.Sprintf("\tcase %q:\n", operation)
	start := strings.Index(generated, startMarker)
	if start < 0 {
		t.Fatalf("generated dispatch has no case for %s", operation)
	}
	block := generated[start:]
	nextCase := strings.Index(block[len(startMarker):], "\tcase ")
	if nextCase >= 0 {
		return block[:len(startMarker)+nextCase]
	}
	nextDefault := strings.Index(block[len(startMarker):], "\tdefault:")
	if nextDefault >= 0 {
		return block[:len(startMarker)+nextDefault]
	}
	t.Fatalf("generated dispatch case for %s has no terminator", operation)
	return ""
}
