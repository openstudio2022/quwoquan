package tests

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"quwoquan_service/services/content-service/internal/application"
)

func TestCreateMarkdownArticleContract(t *testing.T) {
	markdown := `---
title: 西湖半日城市漫游
summary: 从湖滨到龙井路
template: journal
fontPreset: clean
coverImage: asset://cover
---
# 西湖半日城市漫游

第一段正文。

![封面](asset://cover)
`
	payload := map[string]any{
		"contentType":            "article",
		"articleMarkdown":        markdown,
		"articleMarkdownVersion": "qwq-rich-md/1",
		"articleAssetManifest": map[string]any{
			"assets": []map[string]any{
				{"assetId": "cover", "scope": "draft", "objectKey": "media/draft/cover.jpg", "sha256": "dev"},
			},
		},
		"articleRenderProfile": map[string]any{"template": "journal", "fontPreset": "clean"},
		"visibility":           "public",
	}
	raw, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}
	created := createDraftPostWithAuthor(t, application.AnonymousFallbackSubAccountID, string(raw))

	if created["articleMarkdown"] == "" {
		t.Fatalf("expected articleMarkdown in response: %+v", created)
	}
	if got, _ := created["articleMarkdownDigest"].(string); !strings.HasPrefix(got, "sha256:") {
		t.Fatalf("expected markdown digest, got %q", got)
	}
	if got := asTestString(created["title"]); got != "西湖半日城市漫游" {
		t.Fatalf("expected front matter title, got %q", got)
	}
	if _, exists := created["articleDocument"]; exists {
		if doc, ok := created["articleDocument"].(map[string]any); ok && len(doc) > 0 {
			t.Fatalf("markdown article should not persist articleDocument: %+v", doc)
		}
	}
}

func TestCreateMarkdownArticleRejectsMissingManifestAsset(t *testing.T) {
	payload := `{
		"contentType": "article",
		"articleMarkdown": "# 标题\n\n![封面](asset://cover)",
		"articleAssetManifest": {"assets": []},
		"visibility": "public"
	}`
	req := httptest.NewRequest(http.MethodPost, "/v1/content/posts", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", application.AnonymousFallbackSubAccountID)
	req.Header.Set("X-Client-Sub-Account-Id", application.AnonymousFallbackSubAccountID)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for missing manifest asset, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestCreateArticleRejectsArticleDocumentOnlyContract(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/posts",
		strings.NewReader(`{
			"contentType":"article",
			"title":"旧长文不再作为写入真相源",
			"articleDocument":{"title":"旧长文不再作为写入真相源","body":"旧格式正文"}
		}`),
	)
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for articleDocument-only article, got %d: %s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "articleMarkdown") {
		t.Fatalf("expected articleMarkdown validation error, got %s", rec.Body.String())
	}
}

func TestBindMediaAssetsToPostContract(t *testing.T) {
	initReq := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/media/uploads:init",
		strings.NewReader(`{"mediaType":"image","assetScope":"draft","sourceKind":"user_upload"}`),
	)
	initReq.Header.Set("Content-Type", "application/json")
	initReq.Header.Set("X-Client-User-Id", application.AnonymousFallbackSubAccountID)
	initRec := httptest.NewRecorder()
	testHandler.ServeHTTP(initRec, initReq)
	if initRec.Code != http.StatusOK {
		t.Fatalf("init upload failed: %d %s", initRec.Code, initRec.Body.String())
	}
	var initResp map[string]any
	if err := json.Unmarshal(initRec.Body.Bytes(), &initResp); err != nil {
		t.Fatalf("decode init response: %v", err)
	}
	sessionID := asTestString(initResp["sessionId"])
	mediaID := asTestString(initResp["mediaId"])

	completeReq := httptest.NewRequest(http.MethodPost, "/v1/content/media/uploads/"+sessionID+":complete", nil)
	completeRec := httptest.NewRecorder()
	testHandler.ServeHTTP(completeRec, completeReq)
	if completeRec.Code != http.StatusOK {
		t.Fatalf("complete upload failed: %d %s", completeRec.Code, completeRec.Body.String())
	}

	post := createDraftPost(t, `{"contentType":"micro","body":"绑定素材测试","visibility":"public"}`)
	postID := asTestString(post["_id"])
	bindReq := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/posts/"+postID+"/media:bind",
		strings.NewReader(`{"assetIds":["`+mediaID+`"]}`),
	)
	bindReq.Header.Set("Content-Type", "application/json")
	bindRec := httptest.NewRecorder()
	testHandler.ServeHTTP(bindRec, bindReq)
	if bindRec.Code != http.StatusOK {
		t.Fatalf("bind failed: %d %s", bindRec.Code, bindRec.Body.String())
	}
	var bindResp map[string]any
	if err := json.Unmarshal(bindRec.Body.Bytes(), &bindResp); err != nil {
		t.Fatalf("decode bind response: %v", err)
	}
	if got := int(bindResp["boundCount"].(float64)); got != 1 {
		t.Fatalf("expected boundCount=1, got %d", got)
	}
}
