// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/spec.md#sit-002
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-005
//
// 五步联程（真实进程 HTTP + Mongo + Redis）：
// 发布 → 安全准入（allow 即 published；review/审核分支由
// post_text_publication 安全门 roundtrip 独立覆盖）→ feed 可见 →
// 详情可读 → 互动（赞/评论）计数与 viewer 态回读收敛。
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestTextPublicationLifecycleJourneyThroughHTTP(t *testing.T) {
	cleanPosts(t)
	t.Cleanup(func() { cleanPosts(t) })

	author := "persona-journey-author"
	viewer := "persona-journey-viewer"

	// 第 1 步：发布（底栏加号语义的 micro 文字发布）。
	publishBody := `{
		"publishIntentId": "intent-journey-1",
		"localDraftId": "draft-journey-1",
		"contentType": "micro",
		"body": "联程验证：从发布到互动的完整旅程",
		"visibility": "public"
	}`
	publishReq := httptest.NewRequest(
		http.MethodPost,
		"/content/posts:publish",
		strings.NewReader(publishBody),
	)
	publishReq.Header.Set("Content-Type", "application/json")
	publishReq.Header.Set("Idempotency-Key", "intent-journey-1")
	publishReq.Header.Set("X-Client-User-Id", author)
	publishReq.Header.Set("X-Client-Persona-Id", author)
	publishRes := httptest.NewRecorder()
	testHandler.ServeHTTP(publishRes, publishReq)
	if publishRes.Code != http.StatusAccepted {
		t.Fatalf(
			"publish status=%d body=%s",
			publishRes.Code,
			publishRes.Body.String(),
		)
	}
	var receipt struct {
		PostID string `json:"postId"`
		State  string `json:"state"`
	}
	if err := json.Unmarshal(publishRes.Body.Bytes(), &receipt); err != nil {
		t.Fatalf("decode publish receipt: %v", err)
	}
	// 第 2 步：安全准入放行 → 立即 published（未获批准不公开的 review 分支
	// 由 TestTextPublicationSafetyAndModerationRoundTripThroughHTTP 覆盖）。
	if receipt.State != "published" || receipt.PostID == "" {
		t.Fatalf("publish receipt=%+v want published with postId", receipt)
	}

	// 第 3 步：另一 viewer 的浏览 feed 立即可见（无需手动刷新投影），
	// 且 viewer 维度 viewerLiked 附着为 false（尚未点赞）。
	feedItem := readJourneyFeedItem(t, viewer, receipt.PostID)
	if liked, present := feedItem["viewerLiked"].(bool); !present || liked {
		t.Fatalf("feed viewerLiked=%v (present=%v) want explicit false", feedItem["viewerLiked"], present)
	}

	// 第 4 步：详情可读。
	detail := readJourneyPostDetail(t, viewer, receipt.PostID)
	if asTestString(detail["body"]) != "联程验证：从发布到互动的完整旅程" {
		t.Fatalf("detail body mismatch: %v", detail["body"])
	}

	// 第 5 步：互动——点赞 + 评论，计数与 viewer 态在公开读面收敛。
	likeReq := httptest.NewRequest(
		http.MethodPost,
		"/content/posts/"+receipt.PostID+"/like",
		nil,
	)
	likeReq.Header.Set("X-Client-User-Id", viewer)
	likeReq.Header.Set("X-Client-Persona-Id", viewer)
	ensureIdempotencyHeader(likeReq, "journey-like")
	likeRes := httptest.NewRecorder()
	testHandler.ServeHTTP(likeRes, likeReq)
	if likeRes.Code != http.StatusOK {
		t.Fatalf("like status=%d body=%s", likeRes.Code, likeRes.Body.String())
	}
	drainReactionOutbox(t)

	createCommentThroughAPI(t, receipt.PostID, viewer, "联程评论：一起见证闭环", "")
	if err := drainCommentOutboxForHarness(context.Background()); err != nil {
		t.Fatalf("drain comment projections: %v", err)
	}

	confirmed := readJourneyPostDetail(t, viewer, receipt.PostID)
	if likeCount, _ := confirmed["likeCount"].(float64); likeCount != 1 {
		t.Fatalf("detail likeCount=%v want 1", confirmed["likeCount"])
	}
	if commentCount, _ := confirmed["commentCount"].(float64); commentCount != 1 {
		t.Fatalf("detail commentCount=%v want 1", confirmed["commentCount"])
	}
	if liked, present := confirmed["viewerLiked"].(bool); !present || !liked {
		t.Fatalf(
			"detail viewerLiked=%v (present=%v) want true after like",
			confirmed["viewerLiked"],
			present,
		)
	}

	// feed 读面同样收敛 viewer 点赞态（换设备/清缓存 hydrate 的服务端真相）。
	likedFeedItem := readJourneyFeedItem(t, viewer, receipt.PostID)
	if liked, present := likedFeedItem["viewerLiked"].(bool); !present || !liked {
		t.Fatalf(
			"feed viewerLiked=%v (present=%v) want true after like",
			likedFeedItem["viewerLiked"],
			present,
		)
	}
	// 作者读自己的 feed 项：未点赞，附着 false 而不是复用他人状态。
	authorFeedItem := readJourneyFeedItem(t, author, receipt.PostID)
	if liked, present := authorFeedItem["viewerLiked"].(bool); !present || liked {
		t.Fatalf(
			"author feed viewerLiked=%v (present=%v) want explicit false",
			authorFeedItem["viewerLiked"],
			present,
		)
	}
}

func readJourneyFeedItem(
	t *testing.T,
	viewerID string,
	postID string,
) map[string]any {
	t.Helper()
	request := httptest.NewRequest(
		http.MethodGet,
		"/content/feed?identity=moment&limit=20",
		nil,
	)
	request.Header.Set("X-Client-User-Id", viewerID)
	request.Header.Set("X-Client-Persona-Id", viewerID)
	response := httptest.NewRecorder()
	testHandler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("feed status=%d body=%s", response.Code, response.Body.String())
	}
	var page struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &page); err != nil {
		t.Fatalf("decode feed page: %v", err)
	}
	for _, item := range page.Items {
		if asTestString(item["postId"]) == postID {
			return item
		}
	}
	t.Fatalf("published post %s not visible in browse feed (%d items)", postID, len(page.Items))
	return nil
}

func readJourneyPostDetail(
	t *testing.T,
	viewerID string,
	postID string,
) map[string]any {
	t.Helper()
	request := httptest.NewRequest(
		http.MethodGet,
		"/content/posts/"+postID,
		nil,
	)
	request.Header.Set("X-Client-User-Id", viewerID)
	request.Header.Set("X-Client-Persona-Id", viewerID)
	response := httptest.NewRecorder()
	testHandler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("detail status=%d body=%s", response.Code, response.Body.String())
	}
	var detail map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &detail); err != nil {
		t.Fatalf("decode detail: %v", err)
	}
	return detail
}
