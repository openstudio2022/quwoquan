// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-001
package local_contract

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	runtimeoperation "quwoquan_service/runtime/operation"
	semantic "quwoquan_service/services/content-service/generated/content/post/semantic_document"
	postgraphql "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/graphql"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	"quwoquan_service/services/content-service/tests/support/semanticfixture"
)

const (
	testContractGraphDigest = "72046cb9d49a8a0e05e57b9c75261d8f5e153f2fed51b6afd1a43f28ee9d62dc"
	testPersistedQueryHash  = "6d1f340a4caedf270c46377b1b3a8ae48e3d669f3f7709ec81b3efcf2f6d9820"

	testArticleMarkdownDigest = "sha256:bc18f7068971a44e264848ecd54b72b02d38216abb8ce3c3d2148e37e8a12398" // sha256("markdown")
	testArticleDocumentDigest = "sha256:43cc23fa52b87b4cc1d02b5b114154151d6adddb17c9fddc06b027fa99e24008" // sha256("document")
	testArticleManifestDigest = "sha256:05b3abf2579a5eb66403cd78be557fd860633a1fe2103c7642030defe32c657f" // sha256("manifest")
	testArticleVersionDigest  = "sha256:5ca4f3850ccc331aaf8a257d6086e526a3b42a63e18cb11d020847985b31d188" // sha256("version")
)

func TestInternalPersistedGetPostExecutesExactOwnerReadSlice(t *testing.T) {
	reader := &recordingPostDetailReader{detail: postports.PostDetailSlice{
		PostID:                 "post-1",
		ContentType:            "article",
		Title:                  "canonical title",
		Body:                   "body",
		Summary:                "summary",
		AuthorPersonaID:        "persona-1",
		AuthorDisplayName:      "Creator",
		AuthorAvatarAssetID:    "avatar-asset-1",
		AuthorAvatarAccessMode: "signed_grant",
		CoverURL:               "https://media.example/post-1.jpg",
		Status:                 "published",
		Visibility:             "public",
		ModerationStatus:       "approved",
		CreatedAt:              time.Date(2026, 8, 11, 0, 0, 0, 0, time.UTC),
		UpdatedAt:              time.Date(2026, 8, 11, 0, 1, 0, 0, time.UTC),
		SourceAttribution: &postports.PostSourceAttributionSlice{
			OriginalCreatorName: "摄影师甲", Platform: "Wikimedia Commons",
			SourcePostURL: "https://example.com/source", OriginalAssetURL: "https://example.com/image.jpg",
			AttributionText: "摄影师甲 / CC BY 4.0", RightsBasis: "CC BY 4.0",
			CommercialAuthorizationStatus: "unverified",
			DerivedModifications:          []string{"crop", "resize"}, WatermarkKind: "author_signature",
			WatermarkNote: "保留作者签名", WatermarkStatus: "present", AudioRightsStatus: "no_audio",
			ModelReleaseStatus: "not_required", PropertyReleaseStatus: "not_required",
			CollectedAt: time.Date(2026, 8, 11, 0, 0, 0, 0, time.UTC), TakedownPolicy: "notice_and_takedown",
		},
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
	if len(detail) != 32 {
		t.Fatalf("selected GraphQL fields=%v", detail)
	}
	if detail["authorAvatarAssetId"] != "avatar-asset-1" || detail["authorAvatarAccessMode"] != "signed_grant" {
		t.Fatalf("avatar media delivery binding=%v", detail)
	}
	if liked, exists := detail["viewerLiked"]; !exists || liked != nil {
		t.Fatalf("internal persisted read must carry viewerLiked=null, got %v", detail["viewerLiked"])
	}
	attribution := detail["sourceAttribution"].(map[string]any)
	modifications := attribution["derivedModifications"].([]any)
	if len(modifications) != 2 || modifications[0] != "crop" || modifications[1] != "resize" ||
		attribution["watermarkKind"] != "author_signature" || attribution["watermarkNote"] != "保留作者签名" ||
		attribution["commercialAuthorizationStatus"] != "unverified" {
		t.Fatalf("GraphQL source attribution facts drifted: %v", attribution)
	}
	for _, field := range []string{"riskAcceptanceId", "publicationAdmission"} {
		if _, exists := attribution[field]; exists {
			t.Fatalf("retired source attribution field %q leaked", field)
		}
	}
	if _, exists := detail["contentIdentity"]; exists {
		t.Fatal("retired contentIdentity leaked into base read slice")
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
		{name: "retired publication admission query hash", body: mutatePayload(validInternalGraphQLPayload(), func(body map[string]any) {
			persistedDescriptor(body)["sha256Hash"] = "eba3ff56ddbac07ac0cf1755ad0f41516b4391533d8e64f33b8613b0e08ef2bb"
		})},
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

func TestInternalPersistedSemanticDocumentPreservesCanonicalEnvelope(t *testing.T) {
	for _, contentType := range []postports.ContentType{"article", "image", "video"} {
		t.Run(string(contentType), func(t *testing.T) {
			doc := semanticfixture.Envelope(t)
			// typed tree 直接往返，保留 children、attributes、sourceMap 和 identity。
			doc.Nodes = []semantic.SemanticNode{{
				NodeID: "section-1", Kind: semantic.NodeKindSection,
				Disposition:          semantic.ProcessingDispositionPreserved,
				RequiredCapabilities: semantic.NodeRegistry[semantic.NodeKindSection].RequiredCapabilities,
				Children: []semantic.SemanticNode{{NodeID: "paragraph-1", Kind: semantic.NodeKindParagraph,
					Attributes: map[string]any{"text": "原始 canonical 内容"}}},
			}}
			doc.RequiredCapabilities = doc.Nodes[0].RequiredCapabilities
			// 按既有 envelope canonical JSON 身份规则更新 fixture，不伪造旧指纹。
			raw, err := json.Marshal(doc)
			if err != nil {
				t.Fatal(err)
			}
			var canonical map[string]any
			if err := json.Unmarshal(raw, &canonical); err != nil {
				t.Fatal(err)
			}
			delete(canonical, "semanticFingerprint")
			delete(canonical, "canonicalDigest")
			raw, err = json.Marshal(canonical)
			if err != nil {
				t.Fatal(err)
			}
			doc.SemanticFingerprint = fmt.Sprintf("sha256:%x", sha256.Sum256(raw))
			canonical["semanticFingerprint"] = doc.SemanticFingerprint
			raw, err = json.Marshal(canonical)
			if err != nil {
				t.Fatal(err)
			}
			doc.CanonicalDigest = fmt.Sprintf("sha256:%x", sha256.Sum256(raw))
			reader := &recordingPostDetailReader{detail: postports.PostDetailSlice{
				PostID: "post-1", ContentType: contentType, SemanticDocument: &doc,
				Status: "published", Visibility: "public", ModerationStatus: "approved",
				ArticleMarkdown: "不得用于重建 semanticDocument",
			}}
			payload := validInternalGraphQLPayload()
			payload["operationName"] = "ContentPostDetailSemantic"
			persistedDescriptor(payload)["sha256Hash"] = "8f01162d0d879ffbdc5e96c93145b5c005b7b03582e52dfaa8c390424c62debd"
			response := httptest.NewRecorder()
			newInternalGraphQLHandler(t, reader).ServeHTTP(response, trustedInternalGraphQLRequest(t, payload))
			if response.Code != http.StatusOK {
				t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
			}
			var envelope struct {
				Data map[string]struct {
					Document json.RawMessage `json:"semanticDocument"`
				} `json:"data"`
			}
			if err := json.Unmarshal(response.Body.Bytes(), &envelope); err != nil {
				t.Fatal(err)
			}
			want, err := json.Marshal(doc)
			if err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(want, envelope.Data["contentPostDetailSemantic"].Document) {
				t.Fatal("GraphQL 改写或丢失了 canonical semantic document")
			}
			reader.detail.SemanticDocument.SchemaVersion = "999.0.0"
			invalid := httptest.NewRecorder()
			newInternalGraphQLHandler(t, reader).ServeHTTP(invalid, trustedInternalGraphQLRequest(t, payload))
			if invalid.Code < 400 {
				t.Fatal("不兼容 semantic envelope 必须 fail closed")
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
			hash:        "8f01162d0d879ffbdc5e96c93145b5c005b7b03582e52dfaa8c390424c62debd",
			root:        "contentPostDetailSemantic",
			operationID: "content.post.GetPostSemantic",
			detail: postports.PostDetailSlice{
				PostID: "post-1", ContentType: "article", TagRefs: []string{"tag-1"},
				EntityRefs: []string{"entity-1"}, SemanticMentions: []postports.PostSemanticMentionSlice{{
					MentionID: "mention-1", Kind: "tag", Surface: "旅行", Location: "body",
					RangeStart: 0, RangeEnd: 2, Status: "published", TargetRef: "tag-1",
				}},
			},
			assert: func(t *testing.T, data map[string]any) {
				if value, exists := data["semanticDocument"]; !exists || value != nil {
					t.Fatalf("nullable canonical slot missing or rebuilt: %v", data)
				}
				if len(data["semanticMentions"].([]any)) != 1 || data["tagRefs"].([]any)[0] != "tag-1" {
					t.Fatalf("semantic data=%v", data)
				}
			},
		},
		{
			name: "media", operationName: "ContentPostDetailMedia",
			hash:        "9d8916aa9564bd99f990ab00b32d79d70dc860d05108a5e6f30f07df43b2a25f",
			root:        "contentPostDetailMedia",
			operationID: "content.post.GetPostMedia",
			detail: postports.PostDetailSlice{
				PostID: "post-1", ContentType: "video", MediaAssetIDs: []string{"asset-1"},
				MediaURLs: []string{"https://media.example/video.mp4"},
				MediaItems: []postports.PostMediaItemSlice{{
					Kind: "video", MediaAssetID: "asset-1", URL: "https://media.example/video.mp4",
					MediaAssetVersion: 2, DurationMS: 1000, Caption: "逐资产说明", AccessMode: "public", CoverAssetID: "cover-1",
				}}, VideoURL: "https://media.example/video.mp4", Width: 1920, Height: 1080,
			},
			assert: func(t *testing.T, data map[string]any) {
				if len(data["mediaItems"].([]any)) != 1 || data["width"] != float64(1920) {
					t.Fatalf("media data=%v", data)
				}
				item := data["mediaItems"].([]any)[0].(map[string]any)
				if item["caption"] != "逐资产说明" || item["accessMode"] != "public" || item["coverAssetId"] != "cover-1" {
					t.Fatalf("media fields lost in GraphQL projection: %v", item)
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
		{name: "semantic", operationName: "ContentPostDetailSemantic", hash: "8f01162d0d879ffbdc5e96c93145b5c005b7b03582e52dfaa8c390424c62debd",
			detail: postports.PostDetailSlice{PostID: "post-1", ContentType: "article", TagRefs: make([]string, 31)}},
		{name: "media", operationName: "ContentPostDetailMedia", hash: "9d8916aa9564bd99f990ab00b32d79d70dc860d05108a5e6f30f07df43b2a25f",
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

type internalGraphQLResearchActiveSupplyReader struct{}

func (internalGraphQLResearchActiveSupplyReader) ActiveSupplySnapshot(
	context.Context,
) (postports.ActiveSupplySnapshot, error) {
	return postports.ActiveSupplySnapshot{
		Environment: "alpha", SourceOwner: "qwq_data", Status: "active",
		ActiveReleaseID: "rel-internal-graphql-research",
		ManifestDigest:  "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		ReadbackStatus:  "passed", Posts: 1,
		ProjectionVersion: 11,
		Revision:          3,
		ActivatedAt:       time.Unix(1_800_000_000, 0).UTC(),
	}, nil
}
