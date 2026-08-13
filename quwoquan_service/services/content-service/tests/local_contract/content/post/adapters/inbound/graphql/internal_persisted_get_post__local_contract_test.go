// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-001
package local_contract

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	runtimeoperation "quwoquan_service/runtime/operation"
	postgraphql "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/graphql"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

const (
	testContractGraphDigest = "72046cb9d49a8a0e05e57b9c75261d8f5e153f2fed51b6afd1a43f28ee9d62dc"
	testPersistedQueryHash  = "3525412614f94647191c1fead96cc6da3bdc452bf0bec9edd92af4793aed3110"

	testArticleMarkdownDigest = "sha256:bc18f7068971a44e264848ecd54b72b02d38216abb8ce3c3d2148e37e8a12398" // sha256("markdown")
	testArticleDocumentDigest = "sha256:43cc23fa52b87b4cc1d02b5b114154151d6adddb17c9fddc06b027fa99e24008" // sha256("document")
	testArticleManifestDigest = "sha256:05b3abf2579a5eb66403cd78be557fd860633a1fe2103c7642030defe32c657f" // sha256("manifest")
	testArticleVersionDigest  = "sha256:5ca4f3850ccc331aaf8a257d6086e526a3b42a63e18cb11d020847985b31d188" // sha256("version")
)

func TestInternalPersistedGetPostExecutesExactOwnerReadSlice(t *testing.T) {
	reader := &recordingPostDetailReader{detail: postports.PostDetailSlice{
		PostID:            "post-1",
		ContentType:       "article",
		Title:             "canonical title",
		Body:              "body",
		Summary:           "summary",
		AuthorPersonaID:   "persona-1",
		AuthorDisplayName: "Creator",
		CoverURL:          "https://media.example/post-1.jpg",
		Status:            "published",
		Visibility:        "public",
		ModerationStatus:  "approved",
		CreatedAt:         time.Date(2026, 8, 11, 0, 0, 0, 0, time.UTC),
		UpdatedAt:         time.Date(2026, 8, 11, 0, 1, 0, 0, time.UTC),
	}}
	handler := newInternalGraphQLHandler(t, reader)
	request := trustedInternalGraphQLRequest(t, validInternalGraphQLPayload())
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	if reader.calls != 1 || reader.postID != "post-1" {
		t.Fatalf("owner read calls=%d postId=%q", reader.calls, reader.postID)
	}
	if reader.operationID != "content.post.GetPost" {
		t.Fatalf("operationId=%q", reader.operationID)
	}
	if reader.viewer.IsAuthenticated() {
		t.Fatal("service principal must not be projected as the post viewer")
	}
	var envelope struct {
		Data struct {
			ContentPostDetail map[string]any `json:"contentPostDetailBase"`
		} `json:"data"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &envelope); err != nil {
		t.Fatal(err)
	}
	detail := envelope.Data.ContentPostDetail
	if detail["postId"] != "post-1" || detail["authorDisplayName"] != "Creator" {
		t.Fatalf("GraphQL data=%v", detail)
	}
	if len(detail) != 31 {
		t.Fatalf("selected GraphQL fields=%v", detail)
	}
	if liked, exists := detail["viewerLiked"]; !exists || liked != nil {
		t.Fatalf("internal persisted read must carry viewerLiked=null, got %v", detail["viewerLiked"])
	}
	if strings.Contains(response.Body.String(), "moderationStatus") {
		t.Fatalf("owner-only field leaked: %s", response.Body.String())
	}
}

func TestInternalPersistedGetPostRejectsIdentityAndBindingDriftBeforeOwnerRead(t *testing.T) {
	tests := []struct {
		name   string
		body   map[string]any
		mutate func(*http.Request)
	}{
		{name: "query text", body: withPayloadField(validInternalGraphQLPayload(), "query", "query ContentPostDetailBase { contentPostDetailBase(postId: \"post-1\") { postId } }")},
		{name: "mutation text", body: withPayloadField(validInternalGraphQLPayload(), "query", "mutation ContentPostDetailBase { deletePost(postId: \"post-1\") }")},
		{name: "operation drift", body: mutatePayload(validInternalGraphQLPayload(), func(body map[string]any) { body["operationName"] = "OtherQuery" })},
		{name: "hash drift", body: mutatePayload(validInternalGraphQLPayload(), func(body map[string]any) { persistedDescriptor(body)["sha256Hash"] = strings.Repeat("a", 64) })},
		{name: "online APQ registration", body: mutatePayload(validInternalGraphQLPayload(), func(body map[string]any) { persistedDescriptor(body)["register"] = true })},
		{name: "extra variable", body: mutatePayload(validInternalGraphQLPayload(), func(body map[string]any) { body["variables"].(map[string]any)["extra"] = true })},
		{name: "graph digest drift", body: validInternalGraphQLPayload(), mutate: func(request *http.Request) {
			request.Header.Set("X-Contract-Graph-SHA256", "sha256:"+strings.Repeat("f", 64))
		}},
		{name: "missing principal", body: validInternalGraphQLPayload(), mutate: func(request *http.Request) { request = request.WithContext(context.Background()) }},
		{name: "wrong service", body: validInternalGraphQLPayload(), mutate: func(request *http.Request) {
			*request = *request.WithContext(servicePrincipalContext(request.Context(), "service:assistant-service", "content.post.graphql.read"))
		}},
		{name: "missing scope", body: validInternalGraphQLPayload(), mutate: func(request *http.Request) {
			*request = *request.WithContext(servicePrincipalContext(request.Context(), "service:api-edge", "other.scope"))
		}},
	}
	for _, testCase := range tests {
		t.Run(testCase.name, func(t *testing.T) {
			reader := &recordingPostDetailReader{detail: postports.PostDetailSlice{PostID: "post-1"}}
			handler := newInternalGraphQLHandler(t, reader)
			request := trustedInternalGraphQLRequest(t, testCase.body)
			if testCase.name == "missing principal" {
				request = request.WithContext(context.Background())
			} else if testCase.mutate != nil {
				testCase.mutate(request)
			}
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code < 400 {
				t.Fatalf("invalid request passed status=%d body=%s", response.Code, response.Body.String())
			}
			if reader.calls != 0 {
				t.Fatalf("invalid request reached owner read %d times", reader.calls)
			}
		})
	}
}

func TestInternalPersistedGetPostExecutesEveryTypeAwareBundleSlice(t *testing.T) {
	tests := []struct {
		name          string
		operationName string
		hash          string
		root          string
		operationID   string
		detail        postports.PostDetailSlice
		assert        func(*testing.T, map[string]any)
	}{
		{
			name: "semantic", operationName: "ContentPostDetailSemantic",
			hash:        "b425b396c13494d91b0e970d0e9c2328d07d549c492bd76537dace26ea74aa04",
			root:        "contentPostDetailSemantic",
			operationID: "content.post.GetPostSemantic",
			detail: postports.PostDetailSlice{
				PostID: "post-1", ContentType: "micro", TagRefs: []string{"tag-1"},
				EntityRefs: []string{"entity-1"}, SemanticMentions: []postports.PostSemanticMentionSlice{{
					MentionID: "mention-1", Kind: "tag", Surface: "旅行", Location: "body",
					RangeStart: 0, RangeEnd: 2, Status: "published", TargetRef: "tag-1",
				}},
			},
			assert: func(t *testing.T, data map[string]any) {
				if len(data["semanticMentions"].([]any)) != 1 || data["tagRefs"].([]any)[0] != "tag-1" {
					t.Fatalf("semantic data=%v", data)
				}
			},
		},
		{
			name: "media", operationName: "ContentPostDetailMedia",
			hash:        "2251d9dca6cc14a77ff40eb630223df0b432095a98c7bd3f9f72d2e8d0752c18",
			root:        "contentPostDetailMedia",
			operationID: "content.post.GetPostMedia",
			detail: postports.PostDetailSlice{
				PostID: "post-1", ContentType: "video", MediaAssetIDs: []string{"asset-1"},
				MediaURLs: []string{"https://media.example/video.mp4"},
				MediaItems: []postports.PostMediaItemSlice{{
					Kind: "video", MediaAssetID: "asset-1", URL: "https://media.example/video.mp4",
					MediaAssetVersion: 2, DurationMS: 1000,
				}}, VideoURL: "https://media.example/video.mp4", Width: 1920, Height: 1080,
			},
			assert: func(t *testing.T, data map[string]any) {
				if len(data["mediaItems"].([]any)) != 1 || data["width"] != float64(1920) {
					t.Fatalf("media data=%v", data)
				}
			},
		},
		{
			name: "article render assets", operationName: "ContentPostDetailArticleRenderAssets",
			hash:        "119359eb546ba50284ad676377ca69138129ca01d605688310292ca156848b38",
			root:        "contentPostDetailArticleRenderAssets",
			operationID: "content.post.GetPostArticleRenderAssets",
			detail: postports.PostDetailSlice{
				PostID: "post-1", ContentType: "article", ArticleMarkdown: "# title",
				ArticleAssetManifest: &postports.PostArticleAssetManifestSlice{
					Schema: "article-asset-manifest", ArticleMarkdownDigest: testArticleMarkdownDigest,
					DocumentSHA256: testArticleDocumentDigest, AssetManifestSHA256: testArticleManifestDigest,
					DocumentVersionSHA256: testArticleVersionDigest,
					Assets:                []postports.PostArticleAssetSlice{{AssetID: "asset-1", PublicSliceKey: "public/key"}},
				},
				ArticleRenderProfile: &postports.PostArticleRenderProfileSlice{Template: "journal"},
			},
			assert: func(t *testing.T, data map[string]any) {
				if len(data["articleAssets"].([]any)) != 1 ||
					data["articleAssetManifestSummary"].(map[string]any)["schema"] != "article-asset-manifest" {
					t.Fatalf("article render data=%v", data)
				}
			},
		},
		{
			name: "article entities", operationName: "ContentPostDetailArticleEntities",
			hash:        "c9206041dca121c2df985c47f57601ccbc256047ade5e4496b2274fd9f9d02fa",
			root:        "contentPostDetailArticleEntities",
			operationID: "content.post.GetPostArticleEntities",
			detail: postports.PostDetailSlice{
				PostID: "post-1", ContentType: "article", EntityMentions: []postports.PostEntityMentionSlice{{
					SubjectType: "homepage", SubjectID: "entity-1", HomepageID: "homepage-1",
					DisplayName: "地点", RangeStart: 0, RangeEnd: 2,
				}},
			},
			assert: func(t *testing.T, data map[string]any) {
				if len(data["entityMentions"].([]any)) != 1 {
					t.Fatalf("article entities=%v", data)
				}
			},
		},
	}
	for _, testCase := range tests {
		t.Run(testCase.name, func(t *testing.T) {
			detail := visibleDetail(testCase.detail)
			reader := &recordingPostDetailReader{detail: detail}
			handler := newInternalGraphQLHandler(t, reader)
			request := trustedInternalGraphQLRequest(t, persistedPayload(testCase.operationName, testCase.hash))
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code != http.StatusOK {
				t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
			}
			if reader.operationID != testCase.operationID {
				t.Fatalf("operationId=%q want=%q", reader.operationID, testCase.operationID)
			}
			var envelope struct {
				Data map[string]map[string]any `json:"data"`
			}
			if err := json.Unmarshal(response.Body.Bytes(), &envelope); err != nil {
				t.Fatal(err)
			}
			data, ok := envelope.Data[testCase.root]
			if !ok {
				t.Fatalf("missing root %s: %v", testCase.root, envelope.Data)
			}
			if data["postId"] != "post-1" || data["contentType"] != string(testCase.detail.ContentType) {
				t.Fatalf("identity data=%v", data)
			}
			testCase.assert(t, data)
		})
	}
}

func TestInternalPersistedGetPostRejectsOversizedOwnerListsWithoutTruncation(t *testing.T) {
	tests := []struct {
		name, operationName, hash string
		detail                    postports.PostDetailSlice
	}{
		{name: "semantic", operationName: "ContentPostDetailSemantic", hash: "b425b396c13494d91b0e970d0e9c2328d07d549c492bd76537dace26ea74aa04",
			detail: postports.PostDetailSlice{PostID: "post-1", ContentType: "micro", TagRefs: make([]string, 31)}},
		{name: "media", operationName: "ContentPostDetailMedia", hash: "2251d9dca6cc14a77ff40eb630223df0b432095a98c7bd3f9f72d2e8d0752c18",
			detail: postports.PostDetailSlice{PostID: "post-1", ContentType: "image", MediaAssetIDs: make([]string, 21)}},
		{name: "article assets", operationName: "ContentPostDetailArticleRenderAssets", hash: "119359eb546ba50284ad676377ca69138129ca01d605688310292ca156848b38",
			detail: postports.PostDetailSlice{PostID: "post-1", ContentType: "article", ArticleAssetManifest: &postports.PostArticleAssetManifestSlice{Assets: make([]postports.PostArticleAssetSlice, 21)}}},
		{name: "article entities", operationName: "ContentPostDetailArticleEntities", hash: "c9206041dca121c2df985c47f57601ccbc256047ade5e4496b2274fd9f9d02fa",
			detail: postports.PostDetailSlice{PostID: "post-1", ContentType: "article", EntityMentions: make([]postports.PostEntityMentionSlice, 31)}},
	}
	for _, testCase := range tests {
		t.Run(testCase.name, func(t *testing.T) {
			reader := &recordingPostDetailReader{detail: visibleDetail(testCase.detail)}
			handler := newInternalGraphQLHandler(t, reader)
			request := trustedInternalGraphQLRequest(t, persistedPayload(testCase.operationName, testCase.hash))
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code < 500 {
				t.Fatalf("oversized owner list status=%d body=%s", response.Code, response.Body.String())
			}
		})
	}
}

func TestInternalPersistedArticleManifestAbsenceReturnsNonNullEmptyAssets(t *testing.T) {
	reader := &recordingPostDetailReader{detail: visibleDetail(postports.PostDetailSlice{
		PostID: "post-1", ContentType: "article",
	})}
	handler := newInternalGraphQLHandler(t, reader)
	request := trustedInternalGraphQLRequest(t, persistedPayload(
		"ContentPostDetailArticleRenderAssets",
		"119359eb546ba50284ad676377ca69138129ca01d605688310292ca156848b38",
	))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	var envelope struct {
		Data map[string]map[string]any `json:"data"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &envelope); err != nil {
		t.Fatal(err)
	}
	data := envelope.Data["contentPostDetailArticleRenderAssets"]
	if data["articleAssetManifestSummary"] != nil {
		t.Fatalf("summary=%v want=null", data["articleAssetManifestSummary"])
	}
	assets, ok := data["articleAssets"].([]any)
	if !ok || len(assets) != 0 {
		t.Fatalf("assets=%T %v want non-null empty list", data["articleAssets"], data["articleAssets"])
	}
}

func visibleDetail(detail postports.PostDetailSlice) postports.PostDetailSlice {
	detail.Status = "published"
	detail.Visibility = "public"
	detail.ModerationStatus = "approved"
	detail.CreatedAt = time.Date(2026, 8, 11, 0, 0, 0, 0, time.UTC)
	detail.UpdatedAt = time.Date(2026, 8, 11, 0, 1, 0, 0, time.UTC)
	return detail
}

type recordingPostDetailReader struct {
	detail      postports.PostDetailSlice
	calls       int
	postID      postports.PostID
	viewer      postports.ViewerContext
	operationID string
}

func (reader *recordingPostDetailReader) FindPostDetail(
	ctx context.Context,
	postID postports.PostID,
) (postports.PostDetailSlice, bool, error) {
	reader.calls++
	reader.postID = postID
	if invocation, ok := runtimeoperation.FromContext(ctx); ok {
		reader.operationID = invocation.OperationID
	}
	return reader.detail, true, nil
}

func newInternalGraphQLHandler(
	t *testing.T,
	reader *recordingPostDetailReader,
) http.Handler {
	t.Helper()
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{Detail: reader})
	handler, err := postgraphql.NewInternalPersistedHandler(facade, testContractGraphDigest)
	if err != nil {
		t.Fatal(err)
	}
	return handler
}

func trustedInternalGraphQLRequest(t *testing.T, body map[string]any) *http.Request {
	t.Helper()
	payload, err := json.Marshal(body)
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(http.MethodPost, "/internal/graphql", bytes.NewReader(payload))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Contract-Graph-SHA256", testContractGraphDigest)
	return request.WithContext(servicePrincipalContext(
		request.Context(), "service:api-edge", "content.post.graphql.read",
	))
}

func servicePrincipalContext(ctx context.Context, subject string, scope string) context.Context {
	return rtauth.WithPrincipal(ctx, rtauth.Principal{Claims: rtauth.Claims{
		Subject: subject,
		Scope:   scope,
		Roles:   []string{"service"},
	}})
}

func validInternalGraphQLPayload() map[string]any {
	return persistedPayload("ContentPostDetailBase", testPersistedQueryHash)
}

func persistedPayload(operationName, hash string) map[string]any {
	return map[string]any{
		"operationName": operationName,
		"variables":     map[string]any{"postId": "post-1"},
		"extensions": map[string]any{
			"persistedQuery": map[string]any{
				"version": 1, "sha256Hash": hash,
			},
		},
	}
}

func withPayloadField(payload map[string]any, key string, value any) map[string]any {
	return mutatePayload(payload, func(body map[string]any) { body[key] = value })
}

func mutatePayload(payload map[string]any, mutate func(map[string]any)) map[string]any {
	encoded, _ := json.Marshal(payload)
	var clone map[string]any
	_ = json.Unmarshal(encoded, &clone)
	mutate(clone)
	return clone
}

func persistedDescriptor(payload map[string]any) map[string]any {
	return payload["extensions"].(map[string]any)["persistedQuery"].(map[string]any)
}
