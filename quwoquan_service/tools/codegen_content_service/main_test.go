package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
)

func TestContentServiceRoutePacketIncludesEveryObjectService(t *testing.T) {
	t.Parallel()

	source, err := contractcodegen.NewSource(
		"../../contracts/metadata",
		validate.ProfileBaseline,
	)
	if err != nil {
		t.Fatalf("NewSource() error = %v", err)
	}
	routes, err := loadServiceRoutes(source, "content-service")
	if err != nil {
		t.Fatalf("loadServiceRoutes() error = %v", err)
	}

	operations := make(map[string]struct{}, len(routes))
	for _, route := range routes {
		operations[route.Operation] = struct{}{}
	}
	for _, operation := range []string{
		"SubmitPostPublication",
		"CreateComment",
		"LikePost",
		"InitMediaUpload",
		"GetMediaAssetReference",
		"GetMediaAssetDeliveryReference",
		"CreateOutboundShare",
		"CreateReport",
		"ListReports",
		"GetReport",
		"BeginReportReview",
		"ResolveReport",
	} {
		if _, found := operations[operation]; !found {
			t.Errorf("route packet is missing %s", operation)
		}
	}
}

func TestContentServiceReadyOperationsDispatchDirectly(t *testing.T) {
	t.Parallel()

	source, err := contractcodegen.NewSource(
		"../../contracts/metadata",
		validate.ProfileBaseline,
	)
	if err != nil {
		t.Fatalf("NewSource() error = %v", err)
	}
	outputDir := t.TempDir()
	if err := generateHTTPScaffold(source, "content-service", outputDir); err != nil {
		t.Fatalf("generateHTTPScaffold() error = %v", err)
	}
	generated, err := os.ReadFile(
		filepath.Join(outputDir, "adapters", "http", "generated_routes.go"),
	)
	if err != nil {
		t.Fatalf("read generated routes: %v", err)
	}

	for operation, handler := range map[string]string{
		"BeginReportReview":              "handleBeginReportReview",
		"BindMediaAssetsToComment":       "handleBindMediaAssetsToComment",
		"CreateComment":                  "handleCreateComment",
		"CreateOutboundShare":            "handleCreateOutboundShare",
		"DeleteComment":                  "handleDeleteComment",
		"GetReport":                      "handleGetReport",
		"GetMediaAssetReference":         "handleGetMediaAssetReference",
		"GetMediaAssetDeliveryReference": "handleGetMediaAssetDeliveryReference",
		"ListCommentReplies":             "handleListCommentReplies",
		"ListComments":                   "handleListComments",
		"ListCommentsByAuthor":           "handleListCommentsByAuthor",
		"ListCommentsForPostAuthor":      "handleListCommentsForPostAuthor",
		"ListReports":                    "handleListReports",
		"PinComment":                     "handleSetCommentPinned",
		"ReactToComment":                 "handleReactToComment",
		"ResolveReport":                  "handleResolveReport",
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
		"ListCommentReplies":       {"postId", "commentId"},
		"ListComments":             {"postId"},
		"PinComment":               {"postId", "commentId"},
		"ReactToComment":           {"commentId"},
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

	source, err := contractcodegen.NewSource(
		"../../contracts/metadata",
		validate.ProfileBaseline,
	)
	if err != nil {
		t.Fatalf("NewSource() error = %v", err)
	}
	outputDir := t.TempDir()
	if err := generateErrorConstants(source, "Post", outputDir); err != nil {
		t.Fatalf("generateErrorConstants() error = %v", err)
	}
	generated, err := os.ReadFile(filepath.Join(outputDir, "generated", "errors.go"))
	if err != nil {
		t.Fatalf("read generated errors: %v", err)
	}
	sourceText := string(generated)
	for _, needle := range []string{
		`rterr.ParseCode("CONTENT.USER.comment_pin_forbidden")`,
		`WithMetadata("forbidden", 403)`,
		`WithMetadata("invalid_argument", 400)`,
	} {
		if !strings.Contains(sourceText, needle) {
			t.Fatalf("generated errors missing %q", needle)
		}
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
