package api_integration

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	runtimemedia "quwoquan_service/runtime/media"
	"quwoquan_service/services/content-service/internal/content/post/application/identity"
)

var helperRequestSequence atomic.Uint64

// submitPublishedPost atomically creates one published Post through the public ABI.
func submitPublishedPost(t *testing.T, payload string) map[string]any {
	t.Helper()
	return submitPublishedPostWithAuthor(t, "", payload)
}

// submitPublishedPostWithAuthor uses distinct authors when recommendation tests
// need multiple items to pass maxAuthorPerFeed reranking.
func submitPublishedPostWithAuthor(t *testing.T, authorID string, payload string) map[string]any {
	t.Helper()
	if strings.TrimSpace(authorID) == "" {
		authorID = identity.AnonymousFallbackPersonaID
	}
	payload = completePublicationFixturePrerequisites(t, authorID, payload)
	req := newPostPublicationRequestForTest(t, authorID, payload)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusAccepted {
		t.Fatalf("submitPublishedPost helper: expected 202, got %d: %s", rec.Code, rec.Body.String())
	}
	var receipt map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &receipt); err != nil {
		t.Fatalf("submitPublishedPost helper: decode receipt: %v", err)
	}
	postID := asTestString(receipt["postId"])
	if postID == "" {
		t.Fatalf("submitPublishedPost helper: receipt missing postId: %+v", receipt)
	}
	drainPostOutbox(t)
	readReq := httptest.NewRequest(http.MethodGet, "/content/posts/"+postID, nil)
	readReq.Header.Set("X-Client-User-Id", authorID)
	readReq.Header.Set("X-Client-Persona-Id", authorID)
	readRec := httptest.NewRecorder()
	testHandler.ServeHTTP(readRec, readReq)
	if readRec.Code != http.StatusOK {
		t.Fatalf("submitPublishedPost helper: read expected 200, got %d: %s", readRec.Code, readRec.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(readRec.Body.Bytes(), &result); err != nil {
		t.Fatalf("submitPublishedPost helper: decode post: %v", err)
	}
	return result
}

func newPostPublicationRequestForTest(
	t *testing.T,
	authorID string,
	payload string,
) *http.Request {
	t.Helper()
	if strings.TrimSpace(authorID) == "" {
		authorID = identity.AnonymousFallbackPersonaID
	}
	var body map[string]any
	if err := json.Unmarshal([]byte(payload), &body); err != nil {
		t.Fatalf("decode publication payload: %v", err)
	}
	sequence := helperRequestSequence.Add(1)
	localDraftID := fmt.Sprintf("api-draft-%d", sequence)
	publishIntentID := fmt.Sprintf("api-publication-%s-%d", authorID, sequence)
	body["localDraftId"] = localDraftID
	body["publishIntentId"] = publishIntentID
	encoded, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("encode publication payload: %v", err)
	}
	req := httptest.NewRequest(
		http.MethodPost,
		"/content/posts:publish",
		strings.NewReader(string(encoded)),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", authorID)
	req.Header.Set("X-Client-Persona-Id", authorID)
	req.Header.Set("Idempotency-Key", publishIntentID)
	req.Header.Set("X-Request-Id", fmt.Sprintf("api-integration-%s", publishIntentID))
	return req
}

func completePublicationFixturePrerequisites(
	t *testing.T,
	authorID string,
	payload string,
) string {
	t.Helper()
	var body map[string]any
	if err := json.Unmarshal([]byte(payload), &body); err != nil {
		t.Fatalf("decode publication fixture: %v", err)
	}
	contentType := strings.TrimSpace(asTestString(body["contentType"]))
	if contentType == "article" &&
		strings.TrimSpace(asTestString(body["articleMarkdown"])) == "" {
		title := strings.TrimSpace(asTestString(body["title"]))
		summary := strings.TrimSpace(asTestString(body["summary"]))
		articleBody := strings.TrimSpace(asTestString(body["body"]))
		coverURL := strings.TrimSpace(asTestString(body["coverUrl"]))
		markdown := ""
		if title != "" {
			markdown += "# " + title + "\n\n"
		}
		if articleBody != "" {
			markdown += articleBody + "\n\n"
		} else if summary != "" {
			markdown += summary + "\n\n"
		}
		if coverURL != "" {
			markdown += "![cover](" + coverURL + ")\n"
		}
		body["articleMarkdown"] = strings.TrimSpace(markdown)
		if strings.TrimSpace(asTestString(body["markdownDialect"])) == "" {
			body["markdownDialect"] = "qwq-rich-md"
		}
		if body["articleAssetManifest"] == nil {
			body["articleAssetManifest"] = map[string]any{
				"schema": "article-asset-manifest",
				"assets": []any{},
			}
		}
		if body["articleRenderProfile"] == nil {
			body["articleRenderProfile"] = map[string]any{
				"template":   "journal",
				"fontPreset": "clean",
			}
		}
	}
	if (contentType == "image" || contentType == "video") &&
		len(asTestStringSlice(body["mediaAssetIds"])) == 0 {
		assetID := createReadyPublicationMediaAsset(t, authorID, contentType)
		body["mediaAssetIds"] = []string{assetID}
	}
	normalized, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("encode publication fixture: %v", err)
	}
	return string(normalized)
}

func createReadyPublicationMediaAsset(
	t *testing.T,
	ownerID string,
	mediaType string,
) string {
	t.Helper()
	assetID := createCompletedUnprocessedMediaAsset(t, ownerID, mediaType)
	if mediaType == "video" {
		markVideoAssetProcessingReady(t, ownerID, assetID)
	} else {
		markImageAssetProcessingReady(t, ownerID, assetID)
	}
	return assetID
}

// createCompletedUnprocessedMediaAsset 只走 init/complete 公开 command，
// 不注入处理结果——供 media_not_ready fail-closed 分支使用。
func createCompletedUnprocessedMediaAsset(
	t *testing.T,
	ownerID string,
	mediaType string,
) string {
	t.Helper()
	sequence := helperRequestSequence.Add(1)
	contentType := "image/jpeg"
	if mediaType == "video" {
		contentType = "video/mp4"
	}
	digest := fmt.Sprintf("sha256:%064x", sequence)
	initBody, err := json.Marshal(map[string]any{
		"mediaType":      mediaType,
		"mimeType":       contentType,
		"fileSize":       128,
		"expectedSha256": digest,
	})
	if err != nil {
		t.Fatal(err)
	}
	initRequest := httptest.NewRequest(
		http.MethodPost,
		"/content/media/uploads:init",
		strings.NewReader(string(initBody)),
	)
	initRequest.Header.Set("Content-Type", "application/json")
	initRequest.Header.Set("X-Client-User-Id", ownerID)
	initRequest.Header.Set("X-Client-Persona-Id", ownerID)
	initRequest.Header.Set("Idempotency-Key", fmt.Sprintf("media-init-%d", sequence))
	initResponse := httptest.NewRecorder()
	testHandler.ServeHTTP(initResponse, initRequest)
	if initResponse.Code != http.StatusOK {
		t.Fatalf(
			"init %s upload failed: %d %s",
			mediaType,
			initResponse.Code,
			initResponse.Body.String(),
		)
	}
	var initialized map[string]any
	if err := json.Unmarshal(initResponse.Body.Bytes(), &initialized); err != nil {
		t.Fatal(err)
	}
	sessionID := asTestString(initialized["sessionId"])

	completeRequest := httptest.NewRequest(
		http.MethodPost,
		"/content/media/uploads/"+sessionID+":complete",
		strings.NewReader(`{"accessPolicy":"owner_only"}`),
	)
	completeRequest.Header.Set("Content-Type", "application/json")
	completeRequest.Header.Set("X-Client-User-Id", ownerID)
	completeRequest.Header.Set("X-Client-Persona-Id", ownerID)
	completeRequest.Header.Set(
		"Idempotency-Key",
		fmt.Sprintf("media-complete-%d", sequence),
	)
	completeResponse := httptest.NewRecorder()
	testHandler.ServeHTTP(completeResponse, completeRequest)
	if completeResponse.Code != http.StatusOK {
		t.Fatalf(
			"complete %s upload failed: %d %s",
			mediaType,
			completeResponse.Code,
			completeResponse.Body.String(),
		)
	}
	var completed map[string]any
	if err := json.Unmarshal(completeResponse.Body.Bytes(), &completed); err != nil {
		t.Fatal(err)
	}
	return asTestString(completed["assetId"])
}

const publicationMediaProcessingTargetVersion int64 = 2

func markVideoAssetProcessingReady(
	t *testing.T,
	ownerID string,
	assetID string,
) {
	t.Helper()
	sequence := helperRequestSequence.Add(1)
	videoPublicSliceKey := runtimemedia.BuildContentMediaPublicSliceKey(
		"video",
		assetID,
		publicationMediaProcessingTargetVersion,
		"video/mp4",
	)
	videoPublicPrefix := strings.TrimSuffix(videoPublicSliceKey, "/source.mp4")
	performMediaCommand(
		t,
		http.MethodPost,
		"/internal/content/media/"+assetID+":processing-result",
		fmt.Sprintf(`{
			"processingStatus":"ready",
			"processorProfile":"media_canary_progressive_mp4",
			"verifiedDurationMs":125000,
			"videoWidth":540,
			"videoHeight":960,
			"videoCodec":"h264",
			"videoContainer":"mp4",
			"videoAudioCodec":"aac",
			"videoKeyframeIntervalMs":2000,
			"videoFastStart":true,
			"videoPublicSliceKey":%q,
			"coverPublicSliceKey":%q,
			"previewTrackVersion":1,
			"previewTrackManifestSliceKey":%q
		}`,
			videoPublicSliceKey,
			videoPublicPrefix+"/cover.webp",
			videoPublicPrefix+"/preview/manifest.json",
		),
		ownerID,
		fmt.Sprintf("media-processing-%d", sequence),
	)
}

func markImageAssetProcessingReady(
	t *testing.T,
	ownerID string,
	assetID string,
) {
	t.Helper()
	sequence := helperRequestSequence.Add(1)
	imagePublicSliceKey := runtimemedia.BuildContentMediaPublicSliceKey(
		"image",
		assetID,
		publicationMediaProcessingTargetVersion,
		"image/jpeg",
	)
	performMediaCommand(
		t,
		http.MethodPost,
		"/internal/content/media/"+assetID+":processing-result",
		fmt.Sprintf(`{
			"processingStatus":"ready",
			"processorProfile":"content_image_normalization",
			"imageWidth":540,
			"imageHeight":960,
			"imageDeliveryMimeType":"image/jpeg",
			"imageNormalizedObjectKey":"media/processed/image/%s/v2/source.jpg",
			"imagePublicSliceKey":%q,
			"imageDominantColor":"#1A2B3C",
			"imageLqip":"data:image/jpeg;base64,/9j/2Q==",
			"imageContentProfile":"photographic",
			"imageDerivativePolicyVersion":1
		}`, assetID, imagePublicSliceKey),
		ownerID,
		fmt.Sprintf("media-processing-%d", sequence),
	)
}

func asTestStringSlice(value any) []string {
	switch typed := value.(type) {
	case []string:
		return typed
	case []any:
		result := make([]string, 0, len(typed))
		for _, item := range typed {
			if text := strings.TrimSpace(asTestString(item)); text != "" {
				result = append(result, text)
			}
		}
		return result
	default:
		return nil
	}
}

func asTestString(value any) string {
	if s, ok := value.(string); ok {
		return s
	}
	return ""
}

func ensureIdempotencyHeader(req *http.Request, suffix string) {
	key := fmt.Sprintf("%s-%d", suffix, helperRequestSequence.Add(1))
	if req.Header.Get("Idempotency-Key") == "" {
		req.Header.Set("Idempotency-Key", key)
	}
	if req.Header.Get("X-Request-Id") == "" {
		req.Header.Set("X-Request-Id", "api-integration-"+key)
	}
}

func TestNormalizePublicationPayloadAddsTypedArticleContract(t *testing.T) {
	t.Parallel()
	normalized := completePublicationFixturePrerequisites(
		t,
		identity.AnonymousFallbackPersonaID,
		`{"contentType":"article","title":"Contract article","body":"Body"}`,
	)
	var payload map[string]any
	if err := json.Unmarshal([]byte(normalized), &payload); err != nil {
		t.Fatal(err)
	}
	if payload["articleMarkdown"] != "# Contract article\n\nBody" ||
		payload["markdownDialect"] != "qwq-rich-md" {
		t.Fatalf("article helper did not produce canonical wire payload: %+v", payload)
	}
}
