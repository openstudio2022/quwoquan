// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/spec.md#open-003
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/post-create-update/spec.md#gwt-004
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-005
//
// 图/视频发布组合联程（真实进程 HTTP + Mongo + Redis）：
// 上传 init/complete → 媒体处理 ready → 发布准入 → 另一 viewer feed
// 可见 → 详情媒体可读。并覆盖 App 轮询语义的服务端契约：媒体未 ready
// 时发布 fail-closed 返回 media_not_ready，ready 后同一 publishIntentId
// 重试成功且不产生重复 Post。
package api_integration

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestImagePublicationLifecycleJourneyThroughHTTP(t *testing.T) {
	cleanPosts(t)
	t.Cleanup(func() { cleanPosts(t) })

	author := "persona-media-journey-author"
	viewer := "persona-media-journey-viewer"

	// 第 1 步：真实上传两张图（init → complete → 处理 ready），与 App
	// ContentMediaUploadCoordinator 同一公开 command 序列。
	firstAsset := createReadyPublicationMediaAsset(t, author, "image")
	secondAsset := createReadyPublicationMediaAsset(t, author, "image")

	// 第 2 步：发布 image Post（显式 mediaAssetIds，不经 fixture 补全）。
	publishBody := fmt.Sprintf(`{
		"publishIntentId": "intent-media-journey-1",
		"localDraftId": "draft-media-journey-1",
		"contentType": "image",
		"body": "图片联程验证：从上传到消费",
		"visibility": "public",
		"mediaAssetIds": [%q, %q]
	}`, firstAsset, secondAsset)
	receipt := submitMediaJourneyPublication(
		t,
		author,
		"intent-media-journey-1",
		publishBody,
	)
	if receipt.State != "published" || receipt.PostID == "" {
		t.Fatalf("publish receipt=%+v want published with postId", receipt)
	}

	// 第 3 步：另一 viewer 的作品浏览 feed 立即可见（图/视频默认
	// contentIdentity=work，与 moment 时间线互斥）。
	feedItem := readMediaJourneyWorkFeedItem(t, viewer, receipt.PostID)
	if got := asTestStringSlice(feedItem["mediaUrls"]); len(got) != 2 {
		t.Fatalf("feed mediaUrls=%v want 2 media urls", feedItem["mediaUrls"])
	}

	// 第 4 步：详情媒体可读——mediaAssetIds 与发布一致。
	detail := readJourneyPostDetail(t, viewer, receipt.PostID)
	assets := asTestStringSlice(detail["mediaAssetIds"])
	if len(assets) != 2 || assets[0] != firstAsset || assets[1] != secondAsset {
		t.Fatalf(
			"detail mediaAssetIds=%v want [%s %s]",
			detail["mediaAssetIds"],
			firstAsset,
			secondAsset,
		)
	}
}

func TestVideoPublicationLifecycleJourneyThroughHTTP(t *testing.T) {
	cleanPosts(t)
	t.Cleanup(func() { cleanPosts(t) })

	author := "persona-video-journey-author"
	viewer := "persona-video-journey-viewer"

	// 上传视频并处理 ready（含 cover/preview slice 物化）。
	videoAsset := createReadyPublicationMediaAsset(t, author, "video")

	publishBody := fmt.Sprintf(`{
		"publishIntentId": "intent-video-journey-1",
		"localDraftId": "draft-video-journey-1",
		"contentType": "video",
		"body": "视频联程验证：从上传到消费",
		"visibility": "public",
		"mediaAssetIds": [%q]
	}`, videoAsset)
	receipt := submitMediaJourneyPublication(
		t,
		author,
		"intent-video-journey-1",
		publishBody,
	)
	if receipt.State != "published" || receipt.PostID == "" {
		t.Fatalf("publish receipt=%+v want published with postId", receipt)
	}

	// viewer 作品浏览 feed 可见。
	feedItem := readMediaJourneyWorkFeedItem(t, viewer, receipt.PostID)
	if coverURL := asTestString(feedItem["coverUrl"]); coverURL == "" {
		t.Fatalf("feed coverUrl empty, want processed video cover url")
	}

	// 详情媒体可读：视频 asset 绑定一致。
	detail := readJourneyPostDetail(t, viewer, receipt.PostID)
	assets := asTestStringSlice(detail["mediaAssetIds"])
	if len(assets) != 1 || assets[0] != videoAsset {
		t.Fatalf("detail mediaAssetIds=%v want [%s]", detail["mediaAssetIds"], videoAsset)
	}
}

func TestImagePublicationFailsClosedUntilMediaReadyThenRetrySucceeds(t *testing.T) {
	cleanPosts(t)
	t.Cleanup(func() { cleanPosts(t) })

	author := "persona-media-retry-author"

	// 只 init+complete、不打处理 ready：发布必须 fail-closed。
	pendingAsset := createCompletedUnprocessedMediaAsset(t, author, "image")
	publishBody := fmt.Sprintf(`{
		"publishIntentId": "intent-media-retry-1",
		"localDraftId": "draft-media-retry-1",
		"contentType": "image",
		"body": "轮询语义验证：未就绪不得发布",
		"visibility": "public",
		"mediaAssetIds": [%q]
	}`, pendingAsset)

	response := performMediaJourneyPublish(
		t,
		author,
		"intent-media-retry-1",
		publishBody,
	)
	if response.Code < 400 || response.Code >= 500 {
		t.Fatalf(
			"publish with unprocessed media status=%d body=%s want 4xx fail-closed",
			response.Code,
			response.Body.String(),
		)
	}
	if !strings.Contains(response.Body.String(), "media_not_ready") {
		t.Fatalf(
			"publish with unprocessed media must surface media_not_ready, got %s",
			response.Body.String(),
		)
	}

	// 媒体处理 ready 后按 App 轮询语义以同一 publishIntentId 重试：成功。
	markImageAssetProcessingReady(t, author, pendingAsset)
	receipt := submitMediaJourneyPublication(
		t,
		author,
		"intent-media-retry-1",
		publishBody,
	)
	if receipt.State != "published" || receipt.PostID == "" {
		t.Fatalf("retry receipt=%+v want published with postId", receipt)
	}
}

type mediaJourneyReceipt struct {
	PostID string `json:"postId"`
	State  string `json:"state"`
}

func readMediaJourneyWorkFeedItem(
	t *testing.T,
	viewerID string,
	postID string,
) map[string]any {
	t.Helper()
	request := httptest.NewRequest(
		http.MethodGet,
		"/content/feed?identity=work&limit=20",
		nil,
	)
	request.Header.Set("X-Client-User-Id", viewerID)
	request.Header.Set("X-Client-Persona-Id", viewerID)
	response := httptest.NewRecorder()
	testHandler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("work feed status=%d body=%s", response.Code, response.Body.String())
	}
	var page struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &page); err != nil {
		t.Fatalf("decode work feed page: %v", err)
	}
	for _, item := range page.Items {
		if asTestString(item["postId"]) == postID {
			return item
		}
	}
	t.Fatalf(
		"published media post %s not visible in work browse feed (%d items)",
		postID,
		len(page.Items),
	)
	return nil
}

func performMediaJourneyPublish(
	t *testing.T,
	authorID string,
	idempotencyKey string,
	payload string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(
		http.MethodPost,
		"/content/posts:publish",
		strings.NewReader(payload),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", idempotencyKey)
	request.Header.Set("X-Client-User-Id", authorID)
	request.Header.Set("X-Client-Persona-Id", authorID)
	response := httptest.NewRecorder()
	testHandler.ServeHTTP(response, request)
	return response
}

func submitMediaJourneyPublication(
	t *testing.T,
	authorID string,
	idempotencyKey string,
	payload string,
) mediaJourneyReceipt {
	t.Helper()
	response := performMediaJourneyPublish(t, authorID, idempotencyKey, payload)
	if response.Code != http.StatusAccepted {
		t.Fatalf("publish status=%d body=%s", response.Code, response.Body.String())
	}
	var receipt mediaJourneyReceipt
	if err := json.Unmarshal(response.Body.Bytes(), &receipt); err != nil {
		t.Fatalf("decode publish receipt: %v", err)
	}
	return receipt
}
