package public_test

import (
	"context"
	"errors"
	rt "quwoquan_service/runtime/search"
	app "quwoquan_service/services/content-service/internal/content/post/application/public"
	"strings"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
type requiredQueries struct {
	err   error
	calls int
}

func (r *requiredQueries) VerifyRequiredQueries(context.Context, rt.ReleaseCandidateBinding) error {
	r.calls++
	return r.err
}

// evaluatorFixture仅提供typed owner事实，判定始终调用真实RequiredQueryEvaluator。
type evaluatorFixture struct {
	at              time.Time
	current         time.Time
	release         rt.ReleaseCandidateBinding
	creator         rt.CreatorSearchCandidateSnapshot
	post            rt.ReleasePostCandidateSnapshot
	homepage        rt.ReleaseHomepageCandidateSnapshot
	mutate          func(*rt.ReleaseQueryReadinessProof)
	elapsed         time.Duration
	ownerElapsed    time.Duration
	searchElapsed   time.Duration
	protectElapsed  time.Duration
	ownerErr        error
	protectErr      error
	protectionCalls int
}

func newEvaluatorFixture(t *testing.T) *evaluatorFixture {
	t.Helper()
	d := "sha256:" + strings.Repeat("a", 64)
	f := &evaluatorFixture{at: time.Date(2026, 9, 13, 0, 0, 0, 0, time.UTC), release: rt.ReleaseCandidateBinding{Environment: "gamma", SourceOwner: "qwq_data", ReleaseID: "local", ManifestDigest: d}}
	f.current = f.at
	f.creator = rt.CreatorSearchCandidateSnapshot{Release: f.release, SourceClosureDigest: d, Profiles: []rt.CreatorSearchPublicSnapshot{}}
	f.post = rt.ReleasePostCandidateSnapshot{Release: f.release, SourceClosureDigest: d, MediaClosureDigest: d, Posts: []rt.ReleasePostPublicSnapshot{}}
	for _, id := range []string{"a", "b"} {
		f.post.Posts = append(f.post.Posts, rt.ReleasePostPublicSnapshot{Identity: rt.ReleaseCandidateObjectIdentity{Release: f.release, ObjectType: "content.post", ObjectID: id, SourceVersion: 1, SourceDigest: d}, PostRef: id, AuthorID: "author-" + id, AuthorDisplayName: "Author", ContentType: "video", Status: "published", Visibility: "public", ModerationStatus: "approved", TagRefs: []string{}, EntityRefs: []string{}, MediaAssetIDs: []string{}, MediaURLs: []string{}, PublishedAt: f.at.Format(time.RFC3339Nano), UpdatedAt: f.at.Format(time.RFC3339Nano), DeepLink: "/post/" + id})
	}
	f.homepage = rt.ReleaseHomepageCandidateSnapshot{Release: f.release, SourceClosureDigest: d, EntityRefMappingDigest: d, Homepages: []rt.ReleaseHomepagePublicSnapshot{}}
	for _, err := range []error{f.creator.Seal(), f.post.Seal(), f.homepage.Seal(), f.creator.Validate(), f.post.Validate(), f.homepage.Validate()} {
		if err != nil {
			t.Fatal("typed fixture invalid", err)
		}
	}
	return f
}
func (f *evaluatorFixture) ReadCreatorCandidate(context.Context, rt.ReleaseCandidateBinding) (rt.CreatorSearchCandidateSnapshot, error) {
	return f.creator, nil
}
func (f *evaluatorFixture) ReadPostCandidate(context.Context, rt.ReleaseCandidateBinding) (rt.ReleasePostCandidateSnapshot, error) {
	return f.post, nil
}
func (f *evaluatorFixture) ReadHomepageCandidate(context.Context, rt.ReleaseCandidateBinding) (rt.ReleaseHomepageCandidateSnapshot, error) {
	return f.homepage, nil
}
func (f *evaluatorFixture) BindingFor(_ context.Context, r rt.ReleaseCandidateBinding, slice string) (rt.ReleaseQueryPreparationBinding, error) {
	return rt.ReleaseQueryPreparationBinding{Release: r, Slice: slice, ProviderBindingGeneration: "sha256:" + strings.Repeat("a", 64), SchemaGeneration: "sha256:" + strings.Repeat("b", 64)}, nil
}
func (f *evaluatorFixture) PrepareSearchRelease(context.Context, rt.ReleaseQueryPreparationBinding, rt.SearchReleaseCandidateSnapshot, int64, string) error {
	return errors.New("pure evaluator must not prepare")
}
func (f *evaluatorFixture) ReadSearchProof(_ context.Context, b rt.ReleaseQueryPreparationBinding, _ string) (rt.ReleaseQueryReadinessProof, error) {
	s := rt.SearchReleaseCandidateSnapshot{Kind: "post", Post: &f.post}
	if b.Slice == "creator_search" {
		s = rt.SearchReleaseCandidateSnapshot{Kind: "creator", Creator: &f.creator}
	} else if b.Slice == "homepage_search" {
		s = rt.SearchReleaseCandidateSnapshot{Kind: "homepage", Homepage: &f.homepage}
	}
	d := "sha256:" + strings.Repeat("d", 64)
	p := rt.ReleaseQueryReadinessProof{Binding: b, SourceClosureDigest: s.SourceClosureDigest(), SnapshotDigest: s.SnapshotDigest(), ObjectSetDigest: s.ObjectSetDigest(), DocumentsDigest: d, CheckpointVersion: 1, VerifiedAt: f.at.Format(time.RFC3339Nano), ValidUntil: f.at.Add(time.Hour).Format(time.RFC3339Nano)}
	for _, q := range []string{"result", "suggest", "retrieval", "ids", "count", "facet"} {
		p.QueryClasses = append(p.QueryClasses, rt.ReleaseQueryClassEvidence{QueryClass: q, ObjectSetDigest: p.ObjectSetDigest, DocumentsDigest: d})
	}
	_ = p.Seal()
	f.current = f.current.Add(f.searchElapsed)
	return p, nil
}
func (f *evaluatorFixture) ReadRecommendationProof(_ context.Context, b rt.ReleaseQueryPreparationBinding, _ string) (rt.ReleaseQueryReadinessProof, error) {
	d := "sha256:" + strings.Repeat("d", 64)
	set, _ := rt.CreatorCanonicalDigest([]map[string]string{{"objectType": "content.post", "objectId": "a"}}, "")
	p := rt.ReleaseQueryReadinessProof{Binding: b, SourceClosureDigest: f.post.SourceClosureDigest, SnapshotDigest: f.post.SnapshotDigest, ObjectSetDigest: f.post.ObjectSetDigest, DocumentsDigest: d, CheckpointVersion: 1, VerifiedAt: f.at.Format(time.RFC3339Nano), ValidUntil: f.at.Add(time.Hour).Format(time.RFC3339Nano), PremiumAdmissionDigest: &d, PremiumObjectSetDigest: &set}
	for _, q := range []string{"home", "premium", "required_detail"} {
		s := p.ObjectSetDigest
		if q == "premium" {
			s = set
		}
		p.QueryClasses = append(p.QueryClasses, rt.ReleaseQueryClassEvidence{QueryClass: q, ObjectSetDigest: s, DocumentsDigest: d})
	}
	if f.mutate != nil {
		f.mutate(&p)
	}
	_ = p.Seal()
	f.current = f.current.Add(f.elapsed)
	return p, nil
}
func (f *evaluatorFixture) VerifyOwnerClosures(context.Context, rt.ReleaseCandidateBinding) error {
	f.current = f.current.Add(f.ownerElapsed)
	return f.ownerErr
}
func (f *evaluatorFixture) VerifyHeld(context.Context, rt.ReleaseCandidateBinding, time.Time) error {
	f.protectionCalls++
	f.current = f.current.Add(f.protectElapsed)
	return f.protectErr
}
func (f *evaluatorFixture) evaluate(t *testing.T) error {
	t.Helper()
	e, err := app.NewRequiredQueryEvaluator(f, f, f, f, f, f, func() time.Time { return f.current })
	if err != nil {
		t.Fatal(err)
	}
	return e.VerifyRequiredQueries(t.Context(), f.release)
}

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
func TestRequiredEvaluatorProofTimeAndSourcePredicates(t *testing.T) {
	cases := []struct {
		name   string
		mutate func(*evaluatorFixture)
		want   error
	}{
		{"current_shape_accepts_full_home_and_premium_subset", func(f *evaluatorFixture) {}, nil},
		{"home_subset_rejected", func(f *evaluatorFixture) {
			f.mutate = func(p *rt.ReleaseQueryReadinessProof) { p.QueryClasses[0].ObjectSetDigest = *p.PremiumObjectSetDigest }
		}, app.ErrReleaseQueryInvalid},
		{"equal_deadline", func(f *evaluatorFixture) {
			f.mutate = func(p *rt.ReleaseQueryReadinessProof) {
				p.ValidUntil = f.at.Add(10 * time.Second).Format(time.RFC3339Nano)
			}
		}, app.ErrReleaseQueryNotReady},
		{"before_deadline", func(f *evaluatorFixture) {
			f.mutate = func(p *rt.ReleaseQueryReadinessProof) {
				p.ValidUntil = f.at.Add(9 * time.Second).Format(time.RFC3339Nano)
			}
		}, app.ErrReleaseQueryNotReady},
		{"expired", func(f *evaluatorFixture) {
			f.mutate = func(p *rt.ReleaseQueryReadinessProof) { p.ValidUntil = f.at.Add(-time.Second).Format(time.RFC3339Nano) }
		}, app.ErrReleaseQueryNotReady},
		{"future_verified_without_clock_authority", func(f *evaluatorFixture) {
			f.mutate = func(p *rt.ReleaseQueryReadinessProof) {
				p.VerifiedAt = f.at.Add(24 * time.Hour).Format(time.RFC3339Nano)
				p.ValidUntil = f.at.Add(25 * time.Hour).Format(time.RFC3339Nano)
			}
		}, app.ErrReleaseQueryInvalid},
		{"invalid_verified_time", func(f *evaluatorFixture) {
			f.mutate = func(p *rt.ReleaseQueryReadinessProof) { p.VerifiedAt = "invalid" }
		}, app.ErrReleaseQueryInvalid},
		{"until_equals_verified", func(f *evaluatorFixture) {
			f.mutate = func(p *rt.ReleaseQueryReadinessProof) { p.VerifiedAt = p.ValidUntil }
		}, app.ErrReleaseQueryInvalid},
		{"until_before_verified", func(f *evaluatorFixture) {
			f.mutate = func(p *rt.ReleaseQueryReadinessProof) {
				p.VerifiedAt = f.at.Add(2 * time.Hour).Format(time.RFC3339Nano)
			}
		}, app.ErrReleaseQueryInvalid},
		{"checkpoint_zero", func(f *evaluatorFixture) {
			f.mutate = func(p *rt.ReleaseQueryReadinessProof) { p.CheckpointVersion = 0 }
		}, app.ErrReleaseQueryInvalid},
		{"checkpoint_negative", func(f *evaluatorFixture) {
			f.mutate = func(p *rt.ReleaseQueryReadinessProof) { p.CheckpointVersion = -1 }
		}, app.ErrReleaseQueryInvalid},
		{"query_consumes_commit_deadline", func(f *evaluatorFixture) { f.elapsed = 11 * time.Second }, app.ErrReleaseQueryNotReady},
		{"owner_query_cannot_reset_budget", func(f *evaluatorFixture) { f.ownerElapsed = 11 * time.Second }, app.ErrReleaseQueryNotReady},
		{"three_search_queries_consume_budget", func(f *evaluatorFixture) { f.searchElapsed = 4 * time.Second }, app.ErrReleaseQueryNotReady},
		{"protection_consumes_deadline", func(f *evaluatorFixture) { f.protectElapsed = 11 * time.Second }, app.ErrReleaseQueryNotReady},
		{"protection_reaches_exact_deadline", func(f *evaluatorFixture) { f.protectElapsed = 10 * time.Second }, app.ErrReleaseQueryNotReady},
		{"non_utc_verified_time", func(f *evaluatorFixture) {
			f.mutate = func(p *rt.ReleaseQueryReadinessProof) { p.VerifiedAt = "2026-09-13T01:00:00+01:00" }
		}, app.ErrReleaseQueryInvalid},
		{"owner_safety_unavailable", func(f *evaluatorFixture) { f.ownerErr = app.ErrReleaseQueryNotReady }, app.ErrReleaseQueryNotReady},
		{"generation_protection_unavailable", func(f *evaluatorFixture) { f.protectErr = app.ErrReleaseQueryNotReady }, app.ErrReleaseQueryNotReady},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			f := newEvaluatorFixture(t)
			c.mutate(f)
			err := f.evaluate(t)
			if !errors.Is(err, c.want) {
				t.Fatalf("VerifyRequiredQueries()=%v; want %v", err, c.want)
			}
		})
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
func TestRequiredEvaluatorHonorsEarlierContextDeadlineAndCancellation(t *testing.T) {
	f := newEvaluatorFixture(t)
	f.at = time.Now().UTC()
	f.current = f.at
	f.elapsed = 3 * time.Second
	e, err := app.NewRequiredQueryEvaluator(f, f, f, f, f, f, func() time.Time { return f.current })
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithDeadline(t.Context(), f.at.Add(2*time.Second))
	defer cancel()
	if err := e.VerifyRequiredQueries(ctx, f.release); !errors.Is(err, app.ErrReleaseQueryNotReady) {
		t.Fatalf("earlier context deadline ignored: %v", err)
	}
	if f.protectionCalls != 0 {
		t.Fatal("exhausted query reached protection")
	}
	cancelled, stop := context.WithCancel(t.Context())
	stop()
	if err := e.VerifyRequiredQueries(cancelled, f.release); !errors.Is(err, app.ErrReleaseQueryNotReady) {
		t.Fatalf("cancelled invocation accepted: %v", err)
	}
}

func TestUnifiedBarrierRequiresCompleteEvaluator(t *testing.T) {
	release := rt.ReleaseCandidateBinding{"gamma", "qwq_data", "candidate", "sha256:" + strings.Repeat("a", 64)}
	if _, err := app.NewReleaseQueryBarrier(nil); !errors.Is(err, app.ErrReleaseQueryNotReady) {
		t.Fatal(err)
	}
	if err := app.VerifyReleaseQueryActivation(t.Context(), release); !errors.Is(err, app.ErrReleaseQueryNotReady) {
		t.Fatal(err)
	}
	required := &requiredQueries{err: app.ErrReleaseQueryNotReady}
	barrier, err := app.NewReleaseQueryBarrier(required)
	if err != nil {
		t.Fatal(err)
	}
	ctx := app.WithReleaseQueryBarrier(t.Context(), barrier)
	if err = app.VerifyReleaseQueryActivation(ctx, release); !errors.Is(err, app.ErrReleaseQueryNotReady) || required.calls != 1 {
		t.Fatal("incomplete evaluator bypass", err)
	}
	required.err = nil
	if err = app.VerifyReleaseQueryActivation(ctx, release); err != nil {
		t.Fatal(err)
	}
	var zero app.ReleaseQueryBarrier
	if err = zero.VerifyActivation(ctx, release); !errors.Is(err, app.ErrReleaseQueryNotReady) {
		t.Fatal("zero barrier bypass", err)
	}
}
