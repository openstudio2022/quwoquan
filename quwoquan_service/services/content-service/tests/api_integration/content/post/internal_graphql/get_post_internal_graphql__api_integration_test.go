// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-001
package api_integration

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	rtauth "quwoquan_service/runtime/auth"
	postgraphql "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/graphql"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	postimport "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func TestInternalGraphQLRequiresVerifiedAPIEdgeCredentialAndReadsPostSlice(t *testing.T) {
	config := internalGraphQLTokenConfig()
	verifier, err := rtauth.NewHS256Verifier(config)
	if err != nil {
		t.Fatal(err)
	}
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		config,
		"api-edge",
		[]string{postgraphql.RequiredServiceScope},
	)
	if err != nil {
		t.Fatal(err)
	}
	reader := &apiPostDetailReader{detail: importedImageDetail(t)}
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{Detail: reader})
	handler, err := postgraphql.NewInternalPersistedHandler(
		facade,
		strings.Repeat("7", 64),
	)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier: verifier,
	})(handler))
	defer server.Close()

	authorization, err := credentials.AuthorizationHeader(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	request, err := http.NewRequest(
		http.MethodPost,
		server.URL+postgraphql.InternalGraphQLPath,
		bytes.NewBufferString(basePersistedGraphQLRequest),
	)
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Contract-Graph-SHA256", strings.Repeat("7", 64))
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	body, _ := io.ReadAll(response.Body)
	if response.StatusCode != http.StatusOK ||
		!bytes.Contains(body, []byte(`"title":"owner internal GraphQL"`)) {
		t.Fatalf("status=%d body=%s", response.StatusCode, body)
	}
	if reader.calls != 1 || reader.postID != "post-1" {
		t.Fatalf("owner reader calls=%d postId=%q", reader.calls, reader.postID)
	}
	var base struct {
		Data struct {
			Post struct {
				Attribution map[string]any `json:"sourceAttribution"`
			} `json:"contentPostDetailBase"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &base); err != nil {
		t.Fatal(err)
	}
	facts := base.Data.Post.Attribution
	if facts["commercialAuthorizationStatus"] != "unverified" || facts["publicationAdmission"] != "production_release" ||
		facts["watermarkKind"] != "author_signature" || facts["watermarkNote"] != "保留作者签名" {
		t.Fatalf("importer -> BSON query -> GraphQL lost source facts: %s", body)
	}
	modifications, _ := json.Marshal(facts["derivedModifications"])
	if string(modifications) != `["crop","resize"]` {
		t.Fatalf("importer -> HTTP GraphQL lost modification order: %s", body)
	}
	if _, retired := facts["riskAcceptanceId"]; retired {
		t.Fatalf("retired source fact leaked: %s", body)
	}
	mediaRequest, err := http.NewRequest(http.MethodPost, server.URL+postgraphql.InternalGraphQLPath,
		bytes.NewBufferString(`{"operationName":"ContentPostDetailMedia","variables":{"postId":"post-1"},"extensions":{"persistedQuery":{"version":1,"sha256Hash":"9d8916aa9564bd99f990ab00b32d79d70dc860d05108a5e6f30f07df43b2a25f"}}}`))
	if err != nil {
		t.Fatal(err)
	}
	mediaRequest.Header = request.Header.Clone()
	mediaResponse, err := http.DefaultClient.Do(mediaRequest)
	if err != nil {
		t.Fatal(err)
	}
	defer mediaResponse.Body.Close()
	mediaBody, err := io.ReadAll(mediaResponse.Body)
	if err != nil {
		t.Fatal(err)
	}
	var media struct {
		Data struct {
			Post struct {
				Items []struct {
					AssetID    string  `json:"mediaAssetId"`
					Caption    *string `json:"caption"`
					AccessMode string  `json:"accessMode"`
				} `json:"mediaItems"`
			} `json:"contentPostDetailMedia"`
		} `json:"data"`
	}
	if err := json.Unmarshal(mediaBody, &media); err != nil {
		t.Fatal(err)
	}
	items := media.Data.Post.Items
	if mediaResponse.StatusCode != http.StatusOK || len(items) != 2 || items[0].AssetID != "asset-b" || items[1].AssetID != "asset-a" ||
		items[0].Caption == nil || *items[0].Caption != "第一图的真实说明" || items[1].Caption != nil || items[0].AccessMode != "public" {
		t.Fatalf("importer -> BSON query -> HTTP GraphQL lost ordered captions: %s", mediaBody)
	}

	forged, err := http.NewRequest(
		http.MethodPost,
		server.URL+postgraphql.InternalGraphQLPath,
		bytes.NewBufferString(basePersistedGraphQLRequest),
	)
	if err != nil {
		t.Fatal(err)
	}
	forged.Header.Set("Content-Type", "application/json")
	forged.Header.Set("X-Contract-Graph-SHA256", strings.Repeat("7", 64))
	forged.Header.Set("X-Client-Account-Id", "service:api-edge")
	forgedResponse, err := http.DefaultClient.Do(forged)
	if err != nil {
		t.Fatal(err)
	}
	defer forgedResponse.Body.Close()
	if forgedResponse.StatusCode != http.StatusUnauthorized {
		forgedBody, _ := io.ReadAll(forgedResponse.Body)
		t.Fatalf("forged identity status=%d body=%s", forgedResponse.StatusCode, forgedBody)
	}
	if reader.calls != 2 {
		t.Fatalf("forged identity reached owner reader; calls=%d", reader.calls)
	}
}

const basePersistedGraphQLRequest = `{"operationName":"ContentPostDetailBase","variables":{"postId":"post-1"},"extensions":{"persistedQuery":{"version":1,"sha256Hash":"7e03c295fb73f2aaed2e8f944d7133b19a02dabd6a3ccc297b7f9f0b16b588d7"}}}`

type apiPostDetailReader struct {
	detail postports.PostDetailSlice
	calls  int
	postID postports.PostID
}

func (reader *apiPostDetailReader) FindPostDetail(
	_ context.Context,
	postID postports.PostID,
) (postports.PostDetailSlice, bool, error) {
	reader.calls++
	reader.postID = postID
	return reader.detail, true, nil
}

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-043
func importedImageDetail(t *testing.T) postports.PostDetailSlice {
	t.Helper()
	root := t.TempDir()
	path := filepath.Join(root, "posts/image/图集/测试/1/manifest.json")
	asset := func(id, caption string) map[string]any {
		return map[string]any{
			"assetId": id, "kind": "image", "accessMode": "public", "cdnUrl": "https://example.com/" + id + ".jpg",
			"caption": caption, "sha256": "sha256:" + strings.Repeat("a", 64),
			"sourceCollectionId": "collection", "creator": "摄影师", "collectionPageUrl": "https://example.com/source",
			"rightsAuditStatus": "unverified", "license": "待核验", "termsUrl": "https://example.com/terms",
		}
	}
	manifest := map[string]any{
		"contentId": "image-caption-chain", "version": 1, "sourceType": "data", "variantPurpose": "original", "status": "active",
		"admission":   map[string]any{"processResult": "completed", "qualityResult": "passed", "usageScope": "production", "evidenceRef": "audit/attestation.json", "evidenceDigest": "sha256:" + strings.Repeat("a", 64)},
		"contentType": "image", "contentIdentity": "work", "title": "owner internal GraphQL", "caption": "作品正文不是逐图说明",
		"sourceCollectionId": "collection", "publishedAt": "2026-09-09T00:00:00Z",
		"assets": []any{asset("asset-b", "第一图的真实说明"), asset("asset-a", "")},
		"sourceAttribution": map[string]any{
			"isOriginal": false, "originalCreatorName": "摄影师", "platform": "Commons", "sourcePostUrl": "https://example.com/source",
			"originalAssetUrl": "https://example.com/image.jpg", "attributionText": "摄影师 / CC BY 4.0", "rightsBasis": "CC BY 4.0",
			"commercialAuthorizationStatus": "unverified", "publicationAdmission": "production_release", "derivedModifications": []string{"crop", "resize"},
			"watermarkKind": "author_signature", "watermarkNote": "保留作者签名", "watermarkStatus": "present", "audioRightsStatus": "no_audio",
			"modelReleaseStatus": "not_required", "propertyReleaseStatus": "not_required", "collectedAt": "2026-09-09T00:00:00Z", "takedownPolicy": "notice_and_takedown",
		},
	}
	raw, err := json.Marshal(manifest)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, raw, 0o644); err != nil {
		t.Fatal(err)
	}
	posts, err := postimport.LoadPosts(root, map[string]bool{"image/图集/测试/1": true})
	if err != nil {
		t.Fatal(err)
	}
	if len(posts) != 1 {
		t.Fatalf("want one imported image: %v", posts)
	}
	post := posts[0]
	media := postimport.ImportedMediaFields(post.Assets, "public")
	raw, err = bson.Marshal(bson.M{
		"_id": "post-1", "contentType": post.ContentType, "contentIdentity": post.ContentIdentity, "title": post.Title, "body": post.Body,
		"mediaItems": media.MediaItems, "sourceAttribution": post.SourceAttribution,
		"status": "published", "visibility": "public", "moderationStatus": "approved", "createdAt": post.CreatedAt, "updatedAt": post.UpdatedAt,
	})
	if err != nil {
		t.Fatal(err)
	}
	var detail postports.PostDetailSlice
	if err := bson.Unmarshal(raw, &detail); err != nil {
		t.Fatal(err)
	}
	if detail.PostID != "post-1" || detail.SourceAttribution == nil || detail.SourceAttribution.CollectedAt.IsZero() || len(detail.MediaItems) != 2 {
		t.Fatalf("importer BSON query binding is incomplete: %+v", detail)
	}
	return detail
}

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-042
func TestImportedArticleEntityMappingReachesTypedGraphQL(t *testing.T) {
	root := t.TempDir()
	write := func(relative string, value any) {
		t.Helper()
		path := filepath.Join(root, relative)
		raw, err := json.Marshal(value)
		if err != nil {
			t.Fatal(err)
		}
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, raw, 0o644); err != nil {
			t.Fatal(err)
		}
	}
	binding := postimport.ReleaseBinding{ReleaseID: "mentions", SourceOwner: "qwq_data", ManifestDigest: "sha256:" + strings.Repeat("a", 64)}
	mappingBytes := []byte(`[{"entityRef":"chengdu-park","homepageId":"hp-cd-verified"},{"entityRef":"guangzhou-park","homepageId":"hp-gz-verified"}]`)
	sum := sha256.Sum256(mappingBytes)
	mappingDigest := "sha256:" + hex.EncodeToString(sum[:])
	closure := "sha256:" + strings.Repeat("b", 64)
	write("report.json", map[string]any{
		"schema": "quwoquan_service.homepage_import_report", "env": "alpha", "releaseId": binding.ReleaseID, "sourceOwner": binding.SourceOwner, "manifestDigest": binding.ManifestDigest,
		"dryRun": false, "expected": 2, "projected": 2, "projectionVersion": 8, "closureDigest": closure, "entityRefMappingDigest": mappingDigest,
		"entityRefToHomepageId": map[string]string{"chengdu-park": "hp-cd-verified", "guangzhou-park": "hp-gz-verified"},
	})
	write("candidate.json", map[string]any{
		"schema": "quwoquan.homepage_release_candidate_receipt", "status": "found", "identity": map[string]string{"environment": "alpha", "releaseId": binding.ReleaseID, "sourceOwner": binding.SourceOwner, "manifestDigest": binding.ManifestDigest},
		"counts": map[string]int{"expected": 2, "projected": 2}, "projectionVersion": 8, "closureDigest": closure, "entityRefMappingDigest": mappingDigest,
	})
	write("entities/地点/中国/四川/成都/公园/p0007/人民公园/3/manifest.json", map[string]string{"entityId": "entity:park-cd", "entityRef": "/entity/chengdu-park", "label": "人民公园"})
	write("entities/地点/中国/广东/广州/公园/p0001/人民公园/8/manifest.json", map[string]string{"entityId": "entity:park-gz", "entityRef": "/entity/guangzhou-park", "label": "人民公园"})
	postPath := "posts/article/导览/p0001/同名公园/1"
	write(postPath+"/manifest.json", map[string]any{
		"contentId": "same-name-parks", "version": 1, "sourceType": "data", "variantPurpose": "original", "status": "active", "contentIdentity": "work", "contentType": "article",
		"publishTitle": "同名公园", "publishedAt": "2026-09-09T00:00:00Z",
		"admission": map[string]any{"processResult": "completed", "qualityResult": "passed", "usageScope": "production", "evidenceRef": "review.json", "evidenceDigest": binding.ManifestDigest},
	})
	markdown := "🙂@[人民公园](entity:park-cd)，[人民公园](/entity/guangzhou-park)，@[未收录](entity:absent)"
	if err := os.WriteFile(filepath.Join(root, postPath, "article.md"), []byte(markdown), 0o644); err != nil {
		t.Fatal(err)
	}
	mapping, err := postimport.LoadHomepageEntityMapping(filepath.Join(root, "report.json"), filepath.Join(root, "candidate.json"), binding, "alpha", false, postimport.ToSet([]string{"chengdu-park", "guangzhou-park"}))
	if err != nil {
		t.Fatal(err)
	}
	posts, err := postimport.LoadPosts(root, map[string]bool{strings.TrimPrefix(postPath, "posts/"): true})
	if err != nil {
		t.Fatal(err)
	}
	if err := postimport.BindPostEntityMentions(posts, root, mapping); err != nil {
		t.Fatal(err)
	}
	document, err := postimport.BuildCanonicalImportedPostDocument(posts[0], time.Now().UTC(), postimport.ImportOptions{}, "active")
	if err != nil {
		t.Fatal(err)
	}
	raw, err := bson.Marshal(document)
	if err != nil {
		t.Fatal(err)
	}
	var detail postports.PostDetailSlice
	if err := bson.Unmarshal(raw, &detail); err != nil {
		t.Fatal(err)
	}
	reader := &apiPostDetailReader{detail: detail}
	handler, err := postgraphql.NewInternalPersistedHandler(postapp.NewPostQueryFacade(postapp.PostQueryDependencies{Detail: reader}), strings.Repeat("7", 64))
	if err != nil {
		t.Fatal(err)
	}
	config := internalGraphQLTokenConfig()
	verifier, err := rtauth.NewHS256Verifier(config)
	if err != nil {
		t.Fatal(err)
	}
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(config, "api-edge", []string{postgraphql.RequiredServiceScope})
	if err != nil {
		t.Fatal(err)
	}
	authorization, err := credentials.AuthorizationHeader(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	requestBody, err := json.Marshal(map[string]any{
		"operationName": "ContentPostDetailArticleEntities", "variables": map[string]string{"postId": string(detail.PostID)},
		"extensions": map[string]any{"persistedQuery": map[string]any{"version": 1, "sha256Hash": "c9206041dca121c2df985c47f57601ccbc256047ade5e4496b2274fd9f9d02fa"}},
	})
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(http.MethodPost, postgraphql.InternalGraphQLPath, bytes.NewReader(requestBody))
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Contract-Graph-SHA256", strings.Repeat("7", 64))
	response := httptest.NewRecorder()
	rtauth.Middleware(rtauth.MiddlewareConfig{AccessTokenVerifier: verifier})(handler).ServeHTTP(response, request)
	var envelope struct {
		Data struct {
			Post struct {
				Mentions []postports.PostEntityMentionSlice `json:"entityMentions"`
			} `json:"contentPostDetailArticleEntities"`
		} `json:"data"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &envelope); err != nil {
		t.Fatal(err)
	}
	mentions := envelope.Data.Post.Mentions
	if response.Code != http.StatusOK || len(mentions) != 2 || mentions[0].SubjectID != "entity:park-cd" || mentions[0].HomepageID != "hp-cd-verified" || mentions[1].SubjectID != "entity:park-gz" || mentions[1].HomepageID != "hp-gz-verified" {
		t.Fatalf("release import -> canonical BSON -> typed owner query -> GraphQL failed: %d %s", response.Code, response.Body.String())
	}
	if reader.calls != 1 || mentions[0].RangeStart != 4 || mentions[0].RangeEnd != 8 || posts[0].ArticleMarkdown != markdown {
		t.Fatal("mention projection changed text, character offsets or per-read request count")
	}
}

func internalGraphQLTokenConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret: []byte("0123456789abcdef0123456789abcdef"),
		Issuer: "https://auth.quwoquan.test", Audience: "quwoquan-api",
		Type: rtauth.TokenTypeAccess, TokenVersion: 1,
		TTL: time.Minute, ClockSkew: time.Second,
	}
}
