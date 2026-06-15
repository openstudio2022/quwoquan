package application

import (
	"context"
	"testing"
	"time"

	rtsearch "quwoquan_service/runtime/search"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

type fakePublishedReader struct {
	posts []postmodel.Post
}

func (f fakePublishedReader) ListPublished(context.Context, int, string) []postmodel.Post {
	return f.posts
}

func retrieveFixturePosts() []postmodel.Post {
	return []postmodel.Post{
		{
			ID: "post_camp", Title: "四川露营旅行攻略", Summary: "营地与路线",
			Body: "整理营地、路线和注意事项", ContentType: "article", Visibility: "public",
			TagRefs: []string{"Topic/旅行/露营"}, AuthorId: "user_alice",
			AuthorDisplayNameSnapshot: "alice", PublishedAt: time.Date(2026, 3, 1, 0, 0, 0, 0, time.UTC),
		},
		{
			ID: "photo_river", Title: "川西风光图集", Summary: "雪山与河谷",
			ContentType: "image", Visibility: "public", AuthorId: "user_bob",
			AuthorDisplayNameSnapshot: "bob", PublishedAt: time.Date(2026, 2, 1, 0, 0, 0, 0, time.UTC),
		},
		{
			ID: "post_walk", Title: "城市散步指南", Summary: "周末散步",
			ContentType: "article", Visibility: "public", AuthorId: "user_alice",
			AuthorDisplayNameSnapshot: "alice", PublishedAt: time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC),
		},
	}
}

func TestPostCandidateSourceMapsContentTargets(t *testing.T) {
	src := PostCandidateSource{reader: fakePublishedReader{posts: retrieveFixturePosts()}}
	plan, _ := rtsearch.PlanRequest(rtsearch.RetrieveRequest{
		Targets: []rtsearch.Target{rtsearch.TargetArticle, rtsearch.TargetPhoto},
	}, rtsearch.Viewer{})
	docs, err := src.Candidates(context.Background(), plan)
	if err != nil {
		t.Fatalf("candidates err=%v", err)
	}
	if len(docs) != 3 {
		t.Fatalf("expected 3 docs, got %d", len(docs))
	}
	var sawArticle, sawPhoto bool
	for _, doc := range docs {
		switch rtsearch.TargetForDocument(doc) {
		case rtsearch.TargetArticle:
			sawArticle = true
		case rtsearch.TargetPhoto:
			sawPhoto = true
		}
		if doc.Fields["authorName"] == "" {
			t.Fatalf("author anchor field missing on %s", doc.ObjectID)
		}
	}
	if !sawArticle || !sawPhoto {
		t.Fatalf("target mapping incomplete article=%v photo=%v", sawArticle, sawPhoto)
	}
}

func TestPostCandidateSourceSkipsWhenNoContentTarget(t *testing.T) {
	src := PostCandidateSource{reader: fakePublishedReader{posts: retrieveFixturePosts()}}
	plan, _ := rtsearch.PlanRequest(rtsearch.RetrieveRequest{
		Targets: []rtsearch.Target{rtsearch.TargetUser},
	}, rtsearch.Viewer{})
	docs, err := src.Candidates(context.Background(), plan)
	if err != nil {
		t.Fatalf("candidates err=%v", err)
	}
	if len(docs) != 0 {
		t.Fatalf("content source must skip when no content target requested, got %d", len(docs))
	}
}

func TestRetrievePostsTextRecallAndAuthorAnchor(t *testing.T) {
	backend := rtsearch.NewNativeStoreBackend(
		PostCandidateSource{reader: fakePublishedReader{posts: retrieveFixturePosts()}},
	)

	// Text recall: "四川露营攻略" ranks the camping article first.
	resp, err := rtsearch.Retrieve(context.Background(), rtsearch.RetrieveRequest{
		Targets: []rtsearch.Target{rtsearch.TargetArticle},
		Terms:   []string{"四川", "露营", "攻略"},
	}, backend, rtsearch.Viewer{})
	if err != nil {
		t.Fatalf("retrieve err=%v", err)
	}
	if len(resp.Hits) == 0 || resp.Hits[0].ObjectID != "post_camp" {
		t.Fatalf("expected post_camp top, got %#v", resp.Hits)
	}

	// names=[alice] anchors to author across article target without type.
	resp, err = rtsearch.Retrieve(context.Background(), rtsearch.RetrieveRequest{
		Targets: []rtsearch.Target{rtsearch.TargetArticle},
		Names:   []string{"alice"},
	}, backend, rtsearch.Viewer{})
	if err != nil {
		t.Fatalf("retrieve err=%v", err)
	}
	if len(resp.Hits) != 2 {
		t.Fatalf("alice authored 2 articles, got %#v", resp.Hits)
	}
}

func TestNormalizeSearchMatchedFieldPreservesContractFieldNames(t *testing.T) {
	postWithoutSummary := postmodel.Post{
		Summary: "",
		Body:    "候选治理中的普通正文",
	}
	if got := normalizeSearchMatchedField("tags", postWithoutSummary); got != "tagRefs" {
		t.Fatalf("expected tags -> tagRefs, got %q", got)
	}
	if got := normalizeSearchMatchedField("entities", postWithoutSummary); got != "entityRefs" {
		t.Fatalf("expected entities -> entityRefs, got %q", got)
	}
	if got := normalizeSearchMatchedField("summary", postWithoutSummary); got != "body" {
		t.Fatalf("expected summary fallback -> body, got %q", got)
	}

	postWithSummary := postmodel.Post{
		Summary: "正文摘要",
		Body:    "正文内容",
	}
	if got := normalizeSearchMatchedField("summary", postWithSummary); got != "summary" {
		t.Fatalf("expected explicit summary to stay summary, got %q", got)
	}
}

func TestGetAppConfigUsesGenericCanaryMatrixPayload(t *testing.T) {
	service := NewPostService(
		persistence.NewPostStore(nil),
		WithStoryRuntimeConfig(StoryRuntimeConfig{
			ExperimentBucket: "rollout_20",
			CurrentStage:     "20%",
			CanaryMatrix: []StoryCanaryStage{
				{Stage: "5%", RolloutPercent: 5},
				{Stage: "20%", RolloutPercent: 20},
			},
		}),
	)

	resp := service.GetAppConfig()
	content, _ := resp["content"].(map[string]any)
	if content == nil {
		t.Fatalf("missing content config: %+v", resp)
	}
	grayRelease, _ := content["gray_release"].(map[string]any)
	if grayRelease == nil {
		t.Fatalf("missing gray release config: %+v", content)
	}
	canaryMatrix, ok := grayRelease["canary_matrix"].([]any)
	if !ok {
		t.Fatalf("canary_matrix should be []any for generic payload, got %T", grayRelease["canary_matrix"])
	}
	if len(canaryMatrix) != 2 {
		t.Fatalf("expected 2 canary stages, got %d", len(canaryMatrix))
	}
}
