package local_contract

import (
	"context"
	"errors"
	"testing"

	"quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

type reasonPoolReader struct {
	reasons []intersection.IntersectionReasonView
	err     error
	calls   int
	viewer  string
}

func (r *reasonPoolReader) Feed(_ context.Context, viewer, _ string, _ int) ([]intersection.IntersectionReasonView, error) {
	r.calls++
	r.viewer = viewer
	return r.reasons, r.err
}

func TestProjectAuthorPostIntersectionsReadsViewerPoolOnceAndMatchesPostIdentity(t *testing.T) {
	reader := &reasonPoolReader{reasons: []intersection.IntersectionReasonView{
		canonicalContentReason("bad", "other-post", "其他作品"),
		canonicalContentReason("match", "post-a", "目标作品"),
	}}
	page := postports.AuthorPostPageSlice{Items: []postports.AuthorPostItemSlice{
		{
			PostID: "post-a", AuthorPersonaID: "author-a",
			PrimaryHomepageID: "homepage-a", PrimaryHomepageType: "place",
			GatheringRef: "gathering-a",
		},
		{PostID: "post-b", AuthorPersonaID: "author-a"},
	}}
	projected, err := postapp.ProjectAuthorPostIntersections(context.Background(), page, "viewer-a", reader)
	if err != nil {
		t.Fatal(err)
	}
	if reader.calls != 1 || reader.viewer != "viewer-a" {
		t.Fatalf("reason pool calls=%d viewer=%q", reader.calls, reader.viewer)
	}
	if len(projected.Items[0].IntersectionReasons) != 1 || projected.Items[0].IntersectionReasons[0].IntersectionID != "match" {
		t.Fatalf("matched reasons=%+v", projected.Items[0].IntersectionReasons)
	}
	if projected.Items[0].PrimaryHomepageID != "homepage-a" ||
		projected.Items[0].PrimaryHomepageType != "place" ||
		projected.Items[0].GatheringRef != "gathering-a" {
		t.Fatalf("author post intersection anchors drifted: %+v", projected.Items[0])
	}
	if len(projected.Items[1].IntersectionReasons) != 0 {
		t.Fatalf("unmatched post leaked reason: %+v", projected.Items[1])
	}
}

func TestProjectAuthorPostIntersectionsRejectsBadReasonAndPropagatesReadFailure(t *testing.T) {
	page := postports.AuthorPostPageSlice{Items: []postports.AuthorPostItemSlice{{PostID: "post-a", AuthorPersonaID: "author-a"}}}
	bad := canonicalContentReason("bad", "post-a", "目标作品")
	bad.PrimarySpans = nil
	projected, err := postapp.ProjectAuthorPostIntersections(context.Background(), page, "viewer-a", &reasonPoolReader{reasons: []intersection.IntersectionReasonView{bad}})
	if err != nil {
		t.Fatal(err)
	}
	if len(projected.Items[0].IntersectionReasons) != 0 {
		t.Fatalf("bad reason must be hidden: %+v", projected.Items[0])
	}

	failure := errors.New("recommendation unavailable")
	_, err = postapp.ProjectAuthorPostIntersections(context.Background(), page, "viewer-a", &reasonPoolReader{err: failure})
	if !errors.Is(err, failure) {
		t.Fatalf("read error=%v", err)
	}
}

func canonicalContentReason(id, postID, title string) intersection.IntersectionReasonView {
	target := &intersection.IntersectionTargetView{ObjectType: "post", ObjectID: postID, ObjectKind: "content", RouteID: "workBrowser"}
	text := "联系人赞过《" + title + "》"
	return intersection.IntersectionReasonView{
		IntersectionID: id, IntersectionClass: "fact", Kind: "coLiked", Dimension: "content",
		ObjectKind: "content", ActionTargetID: postID, DisplayName: title,
		PrimaryText: text, DisplayBinding: intersection.DisplayBindingExplicitLink,
		PrimarySpans: []intersection.IntersectionTextSpanView{{Text: "联系人赞过", Role: "plain"}, {Text: "《" + title + "》", Role: "object", Target: target}},
	}
}
