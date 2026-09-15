package local_contract

// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/typed-post-associations/spec.md#gwt-001
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/typed-post-associations/spec.md#gwt-002
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/typed-post-associations/spec.md#gwt-003
import (
	"context"
	"errors"
	post "quwoquan_service/services/content-service/internal/content/post/application"
	"testing"
)

type associationReader struct {
	kind   post.AssociationKind
	hidden bool
	err    error
}

func (r associationReader) ReadAssociation(_ context.Context, id, author, viewer string) (post.AssociationSummary, bool, error) {
	return post.AssociationSummary{Kind: r.kind, TargetID: id, Title: "真实关联"}, !r.hidden, r.err
}
func TestAssociationKindsRequireOwningReader(t *testing.T) {
	ctx := context.Background()
	for _, kind := range []post.AssociationKind{post.AssociationTopic, post.AssociationNewsEvent, post.AssociationPlace, post.AssociationGathering, post.AssociationCollection} {
		reader := associationReader{kind: kind}
		p := post.AssociationProjector{Tags: reader, Places: reader, Gatherings: reader, Collections: reader}
		rows, err := p.Project(ctx, "author", "viewer", []post.AssociationReference{{Kind: kind, TargetID: "canonical"}})
		if err != nil || len(rows) != 1 || rows[0].Kind != kind {
			t.Fatalf("%s: %+v %v", kind, rows, err)
		}
	}
	p := post.AssociationProjector{Tags: associationReader{kind: post.AssociationNewsEvent}}
	if _, err := p.Project(ctx, "author", "viewer", []post.AssociationReference{{Kind: post.AssociationGathering, TargetID: "news"}}); err == nil {
		t.Fatal("news cannot stand in for participation")
	}
	if _, err := p.Project(ctx, "author", "viewer", []post.AssociationReference{{Kind: post.AssociationPlace, TargetID: "text location"}}); err == nil {
		t.Fatal("text cannot stand in for homepage")
	}
}
func TestAssociationInvisibleAndFailureAreDistinct(t *testing.T) {
	ctx := context.Background()
	ref := []post.AssociationReference{{Kind: post.AssociationPlace, TargetID: "hp"}}
	p := post.AssociationProjector{Places: associationReader{kind: post.AssociationPlace, hidden: true}}
	rows, err := p.Project(ctx, "a", "v", ref)
	if err != nil || len(rows) != 0 {
		t.Fatal(rows, err)
	}
	p.Places = associationReader{kind: post.AssociationPlace, err: errors.New("upstream")}
	if _, err = p.Project(ctx, "a", "v", ref); err == nil {
		t.Fatal("dependency failure became empty success")
	}
}
func TestMediaItemsCannotCreateCollectionAssociation(t *testing.T) {
	p := post.AssociationProjector{}
	rows, err := p.Project(context.Background(), "a", "v", nil)
	if err != nil || len(rows) != 0 {
		t.Fatal(rows, err)
	}
	if _, err = p.Project(context.Background(), "a", "v", []post.AssociationReference{{Kind: post.AssociationCollection, TargetID: "media-item"}}); err == nil {
		t.Fatal("unverified media reference became collection")
	}
}
