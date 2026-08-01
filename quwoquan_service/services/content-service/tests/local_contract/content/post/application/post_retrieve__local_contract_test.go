package post_test

import (
	"context"
	. "quwoquan_service/services/content-service/internal/content/post/application"
	"reflect"
	"testing"
	"time"

	rtsearch "quwoquan_service/runtime/search"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	"quwoquan_service/services/content-service/internal/content/post/application/searchprojection"
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
	src := searchprojection.PostCandidateSource{Reader: fakePublishedReader{posts: retrieveFixturePosts()}}
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

// TestPostCandidateSourceSharesProjection guarantees PostCandidateSource and the
// ES search-index projector consume the very same projection function, so the
// native and ES recall surfaces can never diverge on the post→Document mapping.
func TestPostCandidateSourceSharesProjection(t *testing.T) {
	posts := retrieveFixturePosts()
	src := searchprojection.PostCandidateSource{Reader: fakePublishedReader{posts: posts}}
	plan, _ := rtsearch.PlanRequest(rtsearch.RetrieveRequest{
		Targets: []rtsearch.Target{rtsearch.TargetArticle, rtsearch.TargetPhoto, rtsearch.TargetVideo},
	}, rtsearch.Viewer{})
	docs, err := src.Candidates(context.Background(), plan)
	if err != nil {
		t.Fatalf("candidates err=%v", err)
	}
	if len(docs) != len(posts) {
		t.Fatalf("expected %d docs, got %d", len(posts), len(docs))
	}
	for i, doc := range docs {
		want := searchprojection.ProjectPostToSearchDocument(posts[i])
		if !reflect.DeepEqual(doc, want) {
			t.Fatalf("candidate doc %d diverged from shared projection:\n got=%#v\nwant=%#v", i, doc, want)
		}
	}
}

func TestProjectPostFillsLocationDimension(t *testing.T) {
	post := postmodel.Post{
		ID: "post_geo", Title: "西湖露营", ContentType: "article", Visibility: "public",
		Location:     postmodel.GeoPoint{Latitude: 30.2431, Longitude: 120.1505},
		LocationName: "杭州西湖",
		PublishedAt:  time.Date(2026, 3, 1, 0, 0, 0, 0, time.UTC),
	}
	doc := searchprojection.ProjectPostToSearchDocument(post)
	if doc.Geo == nil || doc.Geo.Lat != 30.2431 || doc.Geo.Lng != 120.1505 {
		t.Fatalf("geo must come from real post location: %#v", doc.Geo)
	}
	if doc.Fields["placeName"] != "杭州西湖" {
		t.Fatalf("placeName=%q want 杭州西湖", doc.Fields["placeName"])
	}
}

func TestProjectPostWithoutCoordsLeavesGeoNil(t *testing.T) {
	post := postmodel.Post{
		ID: "post_nogeo", Title: "随手记", ContentType: "article", Visibility: "public",
		// zero-value Location => no real coordinates captured.
		LocationName: "",
	}
	doc := searchprojection.ProjectPostToSearchDocument(post)
	if doc.Geo != nil {
		t.Fatalf("zero location must leave Geo nil (no fabricated 0,0), got %#v", doc.Geo)
	}
}

func TestPostCandidateSourceSkipsWhenNoContentTarget(t *testing.T) {
	src := searchprojection.PostCandidateSource{Reader: fakePublishedReader{posts: retrieveFixturePosts()}}
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
		searchprojection.PostCandidateSource{Reader: fakePublishedReader{posts: retrieveFixturePosts()}},
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
	if got := NormalizeSearchMatchedField("tags", postWithoutSummary); got != "tagRefs" {
		t.Fatalf("expected tags -> tagRefs, got %q", got)
	}
	if got := NormalizeSearchMatchedField("entities", postWithoutSummary); got != "entityRefs" {
		t.Fatalf("expected entities -> entityRefs, got %q", got)
	}
	if got := NormalizeSearchMatchedField("summary", postWithoutSummary); got != "body" {
		t.Fatalf("expected summary fallback -> body, got %q", got)
	}

	postWithSummary := postmodel.Post{
		Summary: "正文摘要",
		Body:    "正文内容",
	}
	if got := NormalizeSearchMatchedField("summary", postWithSummary); got != "summary" {
		t.Fatalf("expected explicit summary to stay summary, got %q", got)
	}
}
