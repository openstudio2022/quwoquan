package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/content-service/internal/application/identity"
)

func TestSubmitMarkdownArticleContract(t *testing.T) {
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
		"contentType":     "article",
		"articleMarkdown": markdown,
		"markdownDialect": "qwq-rich-md",
		"articleAssetManifest": map[string]any{
			"assets": []map[string]any{
				{"assetId": "cover", "scope": "draft", "objectKey": "media/objects/sha256/aa/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg", "sha256": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
			},
		},
		"articleRenderProfile": map[string]any{"template": "journal", "fontPreset": "clean"},
		"visibility":           "public",
	}
	raw, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}
	created := submitPublishedPostWithAuthor(t, identity.AnonymousFallbackSubAccountID, string(raw))

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

func TestSubmitMarkdownArticleRejectsMissingManifestAsset(t *testing.T) {
	payload := `{
		"contentType": "article",
		"articleMarkdown": "# 标题\n\n![封面](asset://cover)",
		"articleAssetManifest": {"assets": []},
		"visibility": "public"
	}`
	req := newPostPublicationRequestForTest(
		t,
		identity.AnonymousFallbackSubAccountID,
		payload,
	)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for missing manifest asset, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestSubmitArticleRejectsArticleDocumentOnlyContract(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	req := newPostPublicationRequestForTest(
		t,
		identity.AnonymousFallbackSubAccountID,
		`{
			"contentType":"article",
			"title":"旧长文不再作为写入真相源",
			"articleDocument":{"title":"旧长文不再作为写入真相源","body":"旧格式正文"}
		}`,
	)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for articleDocument-only article, got %d: %s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "invalid_argument") {
		t.Fatalf("expected invalid_argument rejection, got %s", rec.Body.String())
	}
}

func TestSubmitPostPublicationBindsReadyOwnedMedia(t *testing.T) {
	initReq := httptest.NewRequest(
		http.MethodPost,
		"/content/media/uploads:init",
		strings.NewReader(`{"mediaType":"image","contentType":"image/jpeg","fileSize":128,"expectedSha256":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}`),
	)
	initReq.Header.Set("Content-Type", "application/json")
	initReq.Header.Set("X-Client-User-Id", identity.AnonymousFallbackSubAccountID)
	initReq.Header.Set("Idempotency-Key", "media-bind-init")
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

	completeReq := httptest.NewRequest(http.MethodPost, "/content/media/uploads/"+sessionID+":complete", strings.NewReader(`{"accessPolicy":"owner_only"}`))
	completeReq.Header.Set("Content-Type", "application/json")
	completeReq.Header.Set("Idempotency-Key", "media-bind-complete")
	completeRec := httptest.NewRecorder()
	testHandler.ServeHTTP(completeRec, completeReq)
	if completeRec.Code != http.StatusOK {
		t.Fatalf("complete upload failed: %d %s", completeRec.Code, completeRec.Body.String())
	}
	var completeResp map[string]any
	if err := json.Unmarshal(completeRec.Body.Bytes(), &completeResp); err != nil {
		t.Fatalf("decode complete response: %v", err)
	}
	mediaID := asTestString(completeResp["assetId"])

	publishIntentID := "media-publication-intent"
	publishReq := httptest.NewRequest(
		http.MethodPost,
		"/content/posts:publish",
		strings.NewReader(`{"publishIntentId":"`+publishIntentID+`","localDraftId":"media-publication-draft","contentType":"image","body":"原子发布素材测试","visibility":"public","mediaAssetIds":["`+mediaID+`"],"mediaItems":[{"kind":"image","mediaId":"`+mediaID+`"}]}`),
	)
	publishReq.Header.Set("Content-Type", "application/json")
	publishReq.Header.Set("X-Client-User-Id", identity.AnonymousFallbackSubAccountID)
	publishReq.Header.Set("Idempotency-Key", publishIntentID)
	publishRec := httptest.NewRecorder()
	testHandler.ServeHTTP(publishRec, publishReq)
	if publishRec.Code != http.StatusAccepted {
		t.Fatalf("atomic publication failed: %d %s", publishRec.Code, publishRec.Body.String())
	}
	var publishResp map[string]any
	if err := json.Unmarshal(publishRec.Body.Bytes(), &publishResp); err != nil {
		t.Fatalf("decode publication response: %v", err)
	}
	postID := asTestString(publishResp["postId"])
	if postID == "" {
		t.Fatalf("publication receipt missing postId: %#v", publishResp)
	}
	readReq := httptest.NewRequest(http.MethodGet, "/content/posts/"+postID, nil)
	readRec := httptest.NewRecorder()
	testHandler.ServeHTTP(readRec, readReq)
	if readRec.Code != http.StatusOK {
		t.Fatalf("get bound post failed: %d %s", readRec.Code, readRec.Body.String())
	}
	var readResp map[string]any
	if err := json.Unmarshal(readRec.Body.Bytes(), &readResp); err != nil {
		t.Fatalf("decode bound post: %v", err)
	}
	mediaURLs, ok := readResp["mediaUrls"].([]any)
	if !ok || len(mediaURLs) != 1 {
		t.Fatalf("bound post must expose one projected media slice, got %#v", readResp["mediaUrls"])
	}
	publicSliceKey := asTestString(mediaURLs[0])
	if !strings.HasPrefix(publicSliceKey, "media/image/s/asset/") ||
		strings.Contains(publicSliceKey, "objects/") ||
		strings.Contains(publicSliceKey, "cdn.test") {
		t.Fatalf("bound post leaked non-public media identity: %q", publicSliceKey)
	}
	if coverURL := asTestString(readResp["coverUrl"]); coverURL != publicSliceKey {
		t.Fatalf("bound image cover must be the same public slice: %q vs %q", coverURL, publicSliceKey)
	}
}

func TestRequestOriginalImageAccessContract(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	eventSpy.Reset()

	initReq := httptest.NewRequest(
		http.MethodPost,
		"/content/media/uploads:init",
		strings.NewReader(`{"mediaType":"image","contentType":"image/jpeg","fileSize":256,"expectedSha256":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}`),
	)
	initReq.Header.Set("Content-Type", "application/json")
	initReq.Header.Set("X-Client-User-Id", identity.AnonymousFallbackSubAccountID)
	initReq.Header.Set("Idempotency-Key", "media-original-init")
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
	if sessionID == "" {
		t.Fatalf("missing media session: %#v", initResp)
	}

	completeReq := httptest.NewRequest(http.MethodPost, "/content/media/uploads/"+sessionID+":complete", strings.NewReader(`{"accessPolicy":"owner_only"}`))
	completeReq.Header.Set("Content-Type", "application/json")
	completeReq.Header.Set("Idempotency-Key", "media-original-complete")
	completeRec := httptest.NewRecorder()
	testHandler.ServeHTTP(completeRec, completeReq)
	if completeRec.Code != http.StatusOK {
		t.Fatalf("complete upload failed: %d %s", completeRec.Code, completeRec.Body.String())
	}
	var completeResp map[string]any
	if err := json.Unmarshal(completeRec.Body.Bytes(), &completeResp); err != nil {
		t.Fatalf("decode complete response: %v", err)
	}
	mediaID := asTestString(completeResp["assetId"])
	if mediaID == "" {
		t.Fatalf("missing completed media asset: %#v", completeResp)
	}

	accessReq := httptest.NewRequest(http.MethodPost, "/content/media/"+mediaID+"/original:access", strings.NewReader(`{"purpose":"view","sessionId":"sess_original_001"}`))
	accessReq.Header.Set("Content-Type", "application/json")
	accessReq.Header.Set("X-Client-User-Id", identity.AnonymousFallbackSubAccountID)
	accessReq.Header.Set("Idempotency-Key", "media-original-access")
	accessRec := httptest.NewRecorder()
	testHandler.ServeHTTP(accessRec, accessReq)
	if accessRec.Code != http.StatusOK {
		t.Fatalf("request original access failed: %d %s", accessRec.Code, accessRec.Body.String())
	}
	var accessResp map[string]any
	if err := json.Unmarshal(accessRec.Body.Bytes(), &accessResp); err != nil {
		t.Fatalf("decode access response: %v", err)
	}
	if accessResp["mediaId"] != mediaID || accessResp["status"] != "granted" {
		t.Fatalf("unexpected access response: %#v", accessResp)
	}
	if !strings.HasPrefix(asTestString(accessResp["originalUrl"]), "https://cdn.test/") {
		t.Fatalf("originalUrl must be issued by Media object gateway: %#v", accessResp)
	}
	if asTestString(accessResp["auditId"]) == "" {
		t.Fatalf("original access must return an audit correlation id: %#v", accessResp)
	}
	replayReq := httptest.NewRequest(http.MethodPost, "/content/media/"+mediaID+"/original:access", strings.NewReader(`{"purpose":"view"}`))
	replayReq.Header.Set("Content-Type", "application/json")
	replayReq.Header.Set("X-Client-User-Id", identity.AnonymousFallbackSubAccountID)
	replayReq.Header.Set("Idempotency-Key", "media-original-access")
	replayRec := httptest.NewRecorder()
	testHandler.ServeHTTP(replayRec, replayReq)
	if replayRec.Code != http.StatusOK {
		t.Fatalf("replay original access failed: %d %s", replayRec.Code, replayRec.Body.String())
	}
	var replayResp map[string]any
	if err := json.Unmarshal(replayRec.Body.Bytes(), &replayResp); err != nil {
		t.Fatalf("decode replay response: %v", err)
	}
	if replayResp["auditId"] != accessResp["auditId"] || replayResp["originalUrl"] != accessResp["originalUrl"] || replayResp["expiresAt"] != accessResp["expiresAt"] {
		t.Fatalf("replay must return the same access grant: first=%#v replay=%#v", accessResp, replayResp)
	}
	count, err := mongoDB.Collection("media_original_access_facts").CountDocuments(context.Background(), bson.M{"_id": accessResp["auditId"]})
	if err != nil {
		t.Fatalf("count original access facts: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected one persisted original access fact, got %d", count)
	}
	outboxCount, err := mongoDB.Collection("media_original_access_outbox").CountDocuments(context.Background(), bson.M{"_id": accessResp["auditId"]})
	if err != nil || outboxCount != 1 {
		t.Fatalf("expected one persisted original access outbox event, count=%d err=%v", outboxCount, err)
	}
}
