// spec_ref: specs/feature-tree/discovery-content/content-display-consistency/viewer-profile-state-sync-contract/spec.md#gwt-001
package feed_test

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	. "quwoquan_service/services/content-service/internal/content/post/application/feed"
	testsupport "quwoquan_service/services/content-service/tests/support"
)

type fixtureViewerReactionReader struct {
	flags       map[string]bool
	err         error
	lastViewer  string
	lastPostIDs []string
}

func (r *fixtureViewerReactionReader) ReadPostLikedFlags(
	_ context.Context,
	viewerPersonaID string,
	postIDs []string,
) (map[string]bool, error) {
	r.lastViewer = viewerPersonaID
	r.lastPostIDs = append([]string(nil), postIDs...)
	if r.err != nil {
		return nil, r.err
	}
	return r.flags, nil
}

func newViewerLikedFixturePost(postID string, now time.Time) postmodel.Post {
	return postmodel.Post{
		ID:              postID,
		ContentType:     "image",
		ContentIdentity: "work",
		AuthorId:        "author-viewer-liked",
		Status:          "published",
		Visibility:      "public",
		Title:           "viewer liked title",
		Body:            "viewer liked body",
		MediaUrls:       []string{"https://media.test/viewer-liked.webp"},
		LikeCount:       5,
		CreatedAt:       now,
		UpdatedAt:       now,
		PublishedAt:     now,
	}
}

func newViewerLikedFeedService(
	posts []postmodel.Post,
	reader FeedViewerReactionReader,
	now time.Time,
) *FeedService {
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	engine := rtrec.NewEngine(
		rtrec.NewSessionCache(
			rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec"))),
			2*time.Second,
			1000,
		),
		[]rtrec.CandidateSource{&captureRecallSource{
			candidates: []rtrec.ContentCandidate{{
				ContentID:   posts[0].ID,
				ContentType: posts[0].ContentType,
				PublishedAt: now,
				RecallPath:  "canonical_release",
			}},
		}},
	)
	opts := testsupport.RankedRecommendationOptions(
		engine,
		readyActiveSupplyOption(),
		WithFeedViewerBlockReader(terminalAllowAllBlockReader{}),
	)
	if reader != nil {
		opts = append(opts, WithFeedViewerReactionReader(reader))
	}
	return NewFeedService(fixtureFeedReader{posts: posts}, opts...)
}

// GWT-001.t1：feed 响应对已登录 viewer 附着服务端权威 viewerLiked；
// 未点赞的 post 附着 false 而不是省略，供端侧 hydrate 收敛本地态。
func TestListFeedAttachesViewerLikedForAuthenticatedViewer(t *testing.T) {
	now := time.Date(2026, time.August, 12, 12, 0, 0, 0, time.UTC)
	postID := "post-viewer-liked-attach"
	reader := &fixtureViewerReactionReader{flags: map[string]bool{postID: true}}
	svc := newViewerLikedFeedService(
		[]postmodel.Post{newViewerLikedFixturePost(postID, now)},
		reader,
		now,
	)

	response, err := svc.ListFeed(context.Background(), ListFeedRequest{
		UserID:          "viewer-liked-user",
		ViewerPersonaID: "persona-viewer-liked",
		SessionID:       "session-viewer-liked",
		Identity:        "work",
		Type:            "image",
		Limit:           1,
	})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	if len(response.Items) != 1 {
		t.Fatalf("items = %d, want 1", len(response.Items))
	}
	if reader.lastViewer != "persona-viewer-liked" {
		t.Fatalf("reader viewer = %q, want persona-viewer-liked", reader.lastViewer)
	}
	item := response.Items[0]
	if item.ViewerLiked == nil || !*item.ViewerLiked {
		t.Fatalf("viewerLiked = %v, want true", item.ViewerLiked)
	}

	// 未点赞（flags 缺失）必须附着 false 而不是 null。
	reader.flags = map[string]bool{}
	response, err = svc.ListFeed(context.Background(), ListFeedRequest{
		UserID:          "viewer-liked-user",
		ViewerPersonaID: "persona-viewer-liked",
		SessionID:       "session-viewer-liked-2",
		Identity:        "work",
		Type:            "image",
		Limit:           1,
	})
	if err != nil {
		t.Fatalf("ListFeed second page: %v", err)
	}
	item = response.Items[0]
	if item.ViewerLiked == nil || *item.ViewerLiked {
		t.Fatalf("viewerLiked = %v, want explicit false", item.ViewerLiked)
	}
	encoded, err := json.Marshal(item)
	if err != nil {
		t.Fatalf("marshal item: %v", err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(encoded, &decoded); err != nil {
		t.Fatalf("decode item: %v", err)
	}
	if liked, present := decoded["viewerLiked"]; !present || liked != false {
		t.Fatalf("wire viewerLiked = %v (present=%v), want false", liked, present)
	}
}

// GWT-001.t1（未附着态）：匿名 viewer 与批量读失败都保持 null（wire 省略），
// 端侧不得据 null 回滚本地状态；读失败静默降级不阻断内容主路径。
func TestListFeedLeavesViewerLikedUnattachedForAnonymousOrReadFailure(t *testing.T) {
	now := time.Date(2026, time.August, 12, 12, 0, 0, 0, time.UTC)
	postID := "post-viewer-liked-null"
	reader := &fixtureViewerReactionReader{flags: map[string]bool{postID: true}}
	svc := newViewerLikedFeedService(
		[]postmodel.Post{newViewerLikedFixturePost(postID, now)},
		reader,
		now,
	)

	// 匿名 viewer：不调用 reader，保持未附着。
	response, err := svc.ListFeed(context.Background(), ListFeedRequest{
		UserID:    "viewer-anonymous",
		SessionID: "session-viewer-anonymous",
		Identity:  "work",
		Type:      "image",
		Limit:     1,
	})
	if err != nil {
		t.Fatalf("ListFeed anonymous: %v", err)
	}
	if len(response.Items) != 1 {
		t.Fatalf("items = %d, want 1", len(response.Items))
	}
	if response.Items[0].ViewerLiked != nil {
		t.Fatalf("anonymous viewerLiked = %v, want nil", *response.Items[0].ViewerLiked)
	}
	if reader.lastViewer != "" {
		t.Fatalf("anonymous request must not call reaction reader, got viewer %q", reader.lastViewer)
	}
	encoded, err := json.Marshal(response.Items[0])
	if err != nil {
		t.Fatalf("marshal anonymous item: %v", err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(encoded, &decoded); err != nil {
		t.Fatalf("decode anonymous item: %v", err)
	}
	if _, present := decoded["viewerLiked"]; present {
		t.Fatalf("anonymous wire must omit viewerLiked, payload=%s", encoded)
	}

	// 批量读失败：feed 主路径不失败，viewerLiked 保持未附着。
	reader.err = errors.New("reaction store unavailable")
	response, err = svc.ListFeed(context.Background(), ListFeedRequest{
		UserID:          "viewer-degraded",
		ViewerPersonaID: "persona-viewer-degraded",
		SessionID:       "session-viewer-degraded",
		Identity:        "work",
		Type:            "image",
		Limit:           1,
	})
	if err != nil {
		t.Fatalf("ListFeed with degraded reaction reader: %v", err)
	}
	if len(response.Items) != 1 {
		t.Fatalf("degraded items = %d, want 1", len(response.Items))
	}
	if response.Items[0].ViewerLiked != nil {
		t.Fatalf("degraded viewerLiked = %v, want nil", *response.Items[0].ViewerLiked)
	}
}
