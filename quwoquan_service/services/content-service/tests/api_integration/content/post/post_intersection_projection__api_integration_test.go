package api_integration

import (
	"context"
	"errors"
	"testing"

	intersectionapp "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
	contenhttp "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

type apiAuthorReasonReader struct {
	reasons []intersectionapp.IntersectionReasonView
	err     error
	calls   int
	viewer  string
}

func (r *apiAuthorReasonReader) Feed(_ context.Context, viewer, _ string, _ int) ([]intersectionapp.IntersectionReasonView, error) {
	r.calls++
	r.viewer = viewer
	return r.reasons, r.err
}

func TestListUserPostsIntersectionProjectionPreservesViewerAndPostIdentity(t *testing.T) {
	target := &intersectionapp.IntersectionTargetView{ObjectType: "post", ObjectID: "post-profile", ObjectKind: "content", RouteID: "workBrowser"}
	reader := &apiAuthorReasonReader{reasons: []intersectionapp.IntersectionReasonView{{
		IntersectionID: "intersection-profile", IntersectionClass: "fact", Kind: "coLiked", Dimension: "content",
		ObjectKind: "content", ActionTargetID: "post-profile", PrimaryText: "联系人赞过《主页作品》",
		DisplayBinding: intersectionapp.DisplayBindingExplicitLink,
		PrimarySpans:   []intersectionapp.IntersectionTextSpanView{{Text: "联系人赞过", Role: "plain"}, {Text: "《主页作品》", Role: "object", Target: target}},
	}}}
	page := postports.AuthorPostPageSlice{Items: []postports.AuthorPostItemSlice{{PostID: "post-profile", AuthorPersonaID: "author-profile"}}}
	projected, err := contenhttp.ProjectAuthorPostsForViewer(context.Background(), page, "viewer-profile", reader)
	if err != nil {
		t.Fatal(err)
	}
	if reader.calls != 1 || reader.viewer != "viewer-profile" {
		t.Fatalf("reader calls=%d viewer=%q", reader.calls, reader.viewer)
	}
	if projected.Items[0].AuthorPersonaID != "author-profile" {
		t.Fatalf("author identity drifted: %+v", projected.Items[0])
	}
	if got := projected.Items[0].IntersectionReasons; len(got) != 1 || got[0].ActionTargetID != "post-profile" {
		t.Fatalf("intersection identity=%+v", got)
	}
}

func TestListUserPostsIntersectionReadFailureKeepsReadableWorks(t *testing.T) {
	page := postports.AuthorPostPageSlice{Items: []postports.AuthorPostItemSlice{{PostID: "post-readable", AuthorPersonaID: "author-readable"}}}
	_, err := contenhttp.ProjectAuthorPostsForViewer(context.Background(), page, "viewer-profile", &apiAuthorReasonReader{err: errors.New("recommendation read failed")})
	if err == nil {
		t.Fatal("expected observable intersection read failure")
	}
	fallback, fallbackErr := contenhttp.ProjectAuthorPostsForViewer(context.Background(), page, "", nil)
	if fallbackErr != nil || len(fallback.Items) != 1 || fallback.Items[0].PostID != "post-readable" {
		t.Fatalf("works fallback=%+v err=%v", fallback, fallbackErr)
	}
}
