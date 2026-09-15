package collection_test

// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/ordered-post-collection/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/ordered-post-collection/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/ordered-post-collection/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/ordered-post-collection/spec.md#gwt-002.t2

import (
	"context"
	"errors"
	app "quwoquan_service/services/content-service/internal/content/post_collection/application"
	domain "quwoquan_service/services/content-service/internal/content/post_collection/domain"
	"slices"
	"testing"
	"time"
)

// 固定对象级端口替身只用于规则测试，不进入生产装配。
type store struct {
	value domain.Collection
	found bool
	fail  bool
}

func (s *store) Find(context.Context, string) (domain.Collection, bool, error) {
	return s.value, s.found, nil
}
func (s *store) CompareAndSwap(_ context.Context, c domain.Collection, v int64) (bool, error) {
	if s.fail {
		return false, errors.New("write unavailable")
	}
	if s.found && s.value.Version != v {
		return false, nil
	}
	s.value = c
	s.found = true
	return true, nil
}

type posts struct {
	hidden map[string]bool
	fail   bool
}

func (p *posts) ReadVisible(_ context.Context, id, viewer string) (app.Member, bool, error) {
	if p.fail {
		return app.Member{}, false, errors.New("upstream failed")
	}
	return app.Member{PostID: id, Title: id, ContentType: map[string]string{"a": "video", "b": "image", "c": "article", "d": "video"}[id]}, !p.hidden[id], nil
}

type covers struct{}

func (covers) CanUseCover(context.Context, string, string, domain.Visibility) (bool, error) {
	return false, nil
}
func setup(t *testing.T) (*app.Service, *store, *posts) {
	t.Helper()
	s := &store{}
	p := &posts{hidden: map[string]bool{}}
	svc, e := app.New(s, p, covers{}, func() time.Time { return time.Unix(1000, 0) })
	if e != nil {
		t.Fatal(e)
	}
	return svc, s, p
}
func command() domain.Save {
	return domain.Save{ID: "collection", Name: "合集", Visibility: domain.Public, PostIDs: []string{"a", "b", "c", "d"}}
}
func TestOwnerLifecycleAndAtomicCAS(t *testing.T) {
	ctx := context.Background()
	svc, s, _ := setup(t)
	in := command()
	r, e := svc.Save(ctx, "owner", in)
	if e != nil || r.Version != 1 {
		t.Fatalf("create: %+v %v", r, e)
	}
	replay, e := svc.Save(ctx, "owner", in)
	if e != nil || replay != r {
		t.Fatalf("replay: %+v %v", replay, e)
	}
	in.ExpectedVersion = 1
	in.PostIDs = []string{"c", "a"}
	r, e = svc.Save(ctx, "owner", in)
	if e != nil || r.Version != 2 || !slices.Equal(s.value.PostIDs, in.PostIDs) {
		t.Fatalf("reorder: %+v %v", r, e)
	}
	if _, e = svc.Save(ctx, "stranger", in); !errors.Is(e, domain.Unavailable) {
		t.Fatal(e)
	}
	in.Name = "stale"
	if _, e = svc.Save(ctx, "owner", in); !errors.Is(e, domain.Conflict) {
		t.Fatal(e)
	}
	in.ExpectedVersion = 2
	in.PostIDs = []string{"a", "a"}
	if _, e = svc.Save(ctx, "owner", in); !errors.Is(e, domain.Invalid) {
		t.Fatal(e)
	}
	r, e = svc.Delete(ctx, "owner", "collection", 2)
	if e != nil || r.Version != 3 || r.Status != domain.Deleted {
		t.Fatalf("delete: %+v %v", r, e)
	}
	if _, e = svc.Get(ctx, "owner", "collection", "", 2); !errors.Is(e, domain.Unavailable) {
		t.Fatal(e)
	}
}
func TestPaginationFiltersBeforeCountingAndRejectsVersionDrift(t *testing.T) {
	ctx := context.Background()
	svc, _, p := setup(t)
	in := command()
	if _, e := svc.Save(ctx, "owner", in); e != nil {
		t.Fatal(e)
	}
	p.hidden["a"] = true
	p.hidden["c"] = true
	page, e := svc.Get(ctx, "reader", "collection", "", 1)
	if e != nil || page.VisibleCount != 2 || len(page.Members) != 1 || page.Members[0].PostID != "b" || page.NextCursor == nil {
		t.Fatalf("page: %+v %v", page, e)
	}
	next, e := svc.Get(ctx, "reader", "collection", *page.NextCursor, 1)
	if e != nil || len(next.Members) != 1 || next.Members[0].PostID != "d" || next.NextCursor != nil {
		t.Fatalf("next: %+v %v", next, e)
	}
	p.hidden["d"] = true
	next, e = svc.Get(ctx, "reader", "collection", *page.NextCursor, 1)
	if e != nil || len(next.Members) != 0 || next.VisibleCount != 1 {
		t.Fatalf("revoked: %+v %v", next, e)
	}
	if _, e = svc.Get(ctx, "another", "collection", *page.NextCursor, 1); !errors.Is(e, domain.Invalid) {
		t.Fatal(e)
	}
	in.ExpectedVersion = 1
	in.Name = "新版"
	if _, e = svc.Save(ctx, "owner", in); e != nil {
		t.Fatal(e)
	}
	if _, e = svc.Get(ctx, "reader", "collection", *page.NextCursor, 1); !errors.Is(e, domain.Conflict) {
		t.Fatal(e)
	}
}
func TestNoDefaultSuccessOnDependencyOrPersistenceFailure(t *testing.T) {
	ctx := context.Background()
	svc, s, p := setup(t)
	s.fail = true
	if _, e := svc.Save(ctx, "owner", command()); !errors.Is(e, domain.StorageWrite) {
		t.Fatal(e)
	}
	if s.found {
		t.Fatal("failed save persisted")
	}
	s.fail = false
	if _, e := svc.Save(ctx, "owner", command()); e != nil {
		t.Fatal(e)
	}
	p.fail = true
	if _, e := svc.Get(ctx, "reader", "collection", "", 20); !errors.Is(e, domain.StorageRead) {
		t.Fatal(e)
	}
	if _, e := svc.Save(ctx, "", command()); !errors.Is(e, domain.Unauthorized) {
		t.Fatal(e)
	}
}
func TestManagementPreservesReferencesWithoutPrivateContent(t *testing.T) {
	ctx := context.Background()
	svc, _, p := setup(t)
	in := command()
	if _, err := svc.Save(ctx, "owner", in); err != nil {
		t.Fatal(err)
	}
	p.hidden["b"] = true
	view, err := svc.GetManagement(ctx, "owner", in.ID)
	if err != nil || len(view.Members) != 4 {
		t.Fatalf("owner management: %+v %v", view, err)
	}
	if view.Members[1].PostID != "b" || view.Members[1].Readable || view.Members[1].Title != nil {
		t.Fatalf("private content leak: %+v", view.Members[1])
	}
	for _, actor := range []string{"", "other"} {
		if _, err := svc.GetManagement(ctx, actor, in.ID); err == nil {
			t.Fatalf("non-owner %q admitted", actor)
		}
	}
	in.ExpectedVersion = view.Version
	in.Name = "保留不可读成员"
	if _, err := svc.Save(ctx, "owner", in); err != nil {
		t.Fatal(err)
	}
	p.fail = true
	if _, err := svc.GetManagement(ctx, "owner", in.ID); !errors.Is(err, domain.StorageRead) {
		t.Fatal("read failure became empty management")
	}
}

func TestPrivateCollectionNeverLeaksToOtherViewer(t *testing.T) {
	ctx := context.Background()
	svc, _, _ := setup(t)
	in := command()
	in.Visibility = domain.Private
	if _, e := svc.Save(ctx, "owner", in); e != nil {
		t.Fatal(e)
	}
	for _, viewer := range []string{"", "other"} {
		if _, e := svc.Get(ctx, viewer, in.ID, "", 10); !errors.Is(e, domain.Unavailable) {
			t.Fatal(e)
		}
	}
}
