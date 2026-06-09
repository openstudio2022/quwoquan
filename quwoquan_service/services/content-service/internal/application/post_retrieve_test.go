package application

import (
	"context"
	"testing"
	"time"

	rtsearch "quwoquan_service/runtime/search"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
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
