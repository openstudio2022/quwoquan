// L2 api_integration: canonical 双 1k 创作者经 match_creator 绑定的真实内容流入发现 feed。
//
// 守护 Phase3 端到端无断点：creator_content.travel_photo_1k_v1.seed.json 的作者绑定（article/image/video）
// 必须能经真实发布管线投影进发现 feed，并以 canonical creator pool 作者身份返回。这条链路证明
// 创作者人设 → 内容载体 → 作者归属 → feed 曝光没有断点。
package tests

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"quwoquan_service/runtime/contractfixture"
)

const canonicalBatchID = "travel_photo_1k_v1"

type creatorContentSeed struct {
	BatchID         string               `json:"batchId"`
	PreviewOnly     bool                 `json:"previewOnly"`
	RoutedBy        string               `json:"routedBy"`
	DistinctAuthors int                  `json:"distinctAuthors"`
	Posts           []creatorContentPost `json:"posts"`
}

type creatorContentPost struct {
	PostID           string `json:"postId"`
	ContentType      string `json:"contentType"`
	Carrier          string `json:"carrier"`
	AuthorID         string `json:"authorId"`
	CreatorProfileID string `json:"creatorProfileId"`
	DisplayName      string `json:"displayName"`
	Title            string `json:"title"`
	Summary          string `json:"summary"`
}

func loadCreatorContentSeed(t *testing.T) creatorContentSeed {
	t.Helper()
	seed, err := contractfixture.LoadMetadataJSON[creatorContentSeed](
		"_shared/test_fixtures/creator_pool/creator_content.travel_photo_1k_v1.seed.json",
	)
	if err != nil {
		t.Fatalf("load creator content seed: %v", err)
	}
	return seed
}

func publishCreatorPost(t *testing.T, post creatorContentPost) {
	t.Helper()
	var payload string
	switch post.Carrier {
	case "image":
		payload = fmt.Sprintf(
			`{"contentType":"image","title":%q,"summary":%q,"mediaUrls":["https://example.com/%s.jpg"],"deviceInfo":{"width":1280,"height":720}}`,
			post.Title, post.Summary, post.PostID,
		)
	case "video":
		payload = fmt.Sprintf(
			`{"contentType":"video","title":%q,"summary":%q,"videoUrl":"https://example.com/%s.mp4"}`,
			post.Title, post.Summary, post.PostID,
		)
	default: // article
		payload = fmt.Sprintf(
			`{"contentType":"article","title":%q,"summary":%q,"body":%q}`,
			post.Title, post.Summary, post.Summary,
		)
	}
	createPostWithAuthor(t, post.AuthorID, payload)
}

// TestCreatorPoolAuthoredContentFlowsToFeed publishes the canonical creator-bound
// content subset through the real publish pipeline and asserts every carrier shows
// up in the discovery feed attributed to its canonical creator author.
func TestCreatorPoolAuthoredContentFlowsToFeed(t *testing.T) {
	requireMongoDB(t)
	t.Cleanup(func() { cleanPosts(t) })

	seed := loadCreatorContentSeed(t)
	if seed.BatchID != canonicalBatchID {
		t.Fatalf("unexpected batch %q", seed.BatchID)
	}
	if seed.PreviewOnly {
		t.Fatal("creator content seed must be production (previewOnly=false)")
	}
	if seed.RoutedBy != "match_creator" {
		t.Fatalf("creator content must be routed by match_creator, got %q", seed.RoutedBy)
	}
	if len(seed.Posts) == 0 {
		t.Fatal("creator content seed has no posts")
	}

	authors := map[string]bool{}
	carriers := map[string]bool{}
	for _, post := range seed.Posts {
		if !strings.HasPrefix(post.AuthorID, "sys_") || !strings.HasSuffix(post.AuthorID, "_sub_01") {
			t.Fatalf("post %s bound to non-canonical creator author %q", post.PostID, post.AuthorID)
		}
		if post.ContentType != post.Carrier {
			t.Fatalf("post %s contentType %q != carrier %q", post.PostID, post.ContentType, post.Carrier)
		}
		authors[post.AuthorID] = true
		carriers[post.Carrier] = true
		publishCreatorPost(t, post)
	}
	if len(authors) != len(seed.Posts) {
		t.Fatalf("expected distinct authors per post, got %d authors for %d posts", len(authors), len(seed.Posts))
	}
	for _, carrier := range []string{"article", "image", "video"} {
		if !carriers[carrier] {
			t.Fatalf("creator content subset missing carrier %q", carrier)
		}
	}

	req := httptest.NewRequest(http.MethodGet, "/v1/content/feed?limit=50", nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("feed: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var page struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &page); err != nil {
		t.Fatalf("decode feed: %v", err)
	}

	feedByTitle := map[string]map[string]any{}
	for _, item := range page.Items {
		if title, ok := item["title"].(string); ok && title != "" {
			feedByTitle[title] = item
		}
	}
	for _, post := range seed.Posts {
		item, ok := feedByTitle[post.Title]
		if !ok {
			t.Fatalf("creator post %q (%s) not found in discovery feed", post.Title, post.Carrier)
		}
		gotAuthor, _ := item["authorId"].(string)
		if gotAuthor != post.AuthorID {
			t.Fatalf("feed item %q author %q != bound author %q", post.Title, gotAuthor, post.AuthorID)
		}
		gotType, _ := item["type"].(string)
		gotContentType, _ := item["contentType"].(string)
		if gotType != post.ContentType && gotContentType != post.ContentType {
			t.Fatalf("feed item %q type %q/%q != %q", post.Title, gotType, gotContentType, post.ContentType)
		}
	}
}
