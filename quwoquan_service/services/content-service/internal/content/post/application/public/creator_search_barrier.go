package public

import (
	"context"
	"errors"
	rt "quwoquan_service/runtime/search"
)

var ErrReleaseQueryNotReady = errors.New("CONTENT.RELEASE.query_barrier_not_ready")
var ErrReleaseQueryInvalid = errors.New("CONTENT.RELEASE.query_barrier_invalid")

// RequiredReleaseQueries只有完整owner证明与代际保护均成立才可准入。
type RequiredReleaseQueries interface {
	VerifyRequiredQueries(context.Context, rt.ReleaseCandidateBinding) error
}
type ReleaseQueryBarrier struct{ required RequiredReleaseQueries }

func NewReleaseQueryBarrier(required RequiredReleaseQueries) (*ReleaseQueryBarrier, error) {
	if required == nil {
		return nil, ErrReleaseQueryNotReady
	}
	return &ReleaseQueryBarrier{required}, nil
}
func (b *ReleaseQueryBarrier) VerifyActivation(ctx context.Context, release rt.ReleaseCandidateBinding) error {
	if b == nil || b.required == nil {
		return ErrReleaseQueryNotReady
	}
	if release.Validate() != nil {
		return ErrReleaseQueryInvalid
	}
	return b.required.VerifyRequiredQueries(ctx, release)
}

type activationBarrierKey struct{}

func WithReleaseQueryBarrier(ctx context.Context, b *ReleaseQueryBarrier) context.Context {
	return context.WithValue(ctx, activationBarrierKey{}, b)
}
func VerifyReleaseQueryActivation(ctx context.Context, release rt.ReleaseCandidateBinding) error {
	b, _ := ctx.Value(activationBarrierKey{}).(*ReleaseQueryBarrier)
	return b.VerifyActivation(ctx, release)
}

type ReleaseSourceQueries interface {
	ReadCreatorCandidate(context.Context, rt.ReleaseCandidateBinding) (rt.CreatorSearchCandidateSnapshot, error)
	ReadPostCandidate(context.Context, rt.ReleaseCandidateBinding) (rt.ReleasePostCandidateSnapshot, error)
	ReadHomepageCandidate(context.Context, rt.ReleaseCandidateBinding) (rt.ReleaseHomepageCandidateSnapshot, error)
}
type SearchPreparationPort interface {
	PrepareSearchRelease(context.Context, rt.ReleaseQueryPreparationBinding, rt.SearchReleaseCandidateSnapshot, int64, string) error
	ReadSearchProof(context.Context, rt.ReleaseQueryPreparationBinding, string) (rt.ReleaseQueryReadinessProof, error)
}
type CandidatePublisher interface {
	Publish(context.Context, rt.ReleaseQueryPreparationBinding, rt.ReleasePostCandidateSnapshot) (string, error)
}
type PreparePostReleaseQueriesCommand struct {
	CreatorBinding                     rt.ReleaseQueryPreparationBinding `json:"creatorBinding"`
	ExpectedCreatorPreparationVersion  int64                             `json:"expectedCreatorPreparationVersion"`
	PostBinding                        rt.ReleaseQueryPreparationBinding `json:"postBinding"`
	HomepageBinding                    rt.ReleaseQueryPreparationBinding `json:"homepageBinding"`
	RecommendationBinding              rt.ReleaseQueryPreparationBinding `json:"recommendationBinding"`
	ExpectedPostPreparationVersion     int64                             `json:"expectedPostPreparationVersion"`
	ExpectedHomepagePreparationVersion int64                             `json:"expectedHomepagePreparationVersion"`
	IdempotencyKey                     string                            `json:"idempotencyKey"`
}
type PostReleaseQueryPreparationResult struct {
	Release              rt.ReleaseCandidateBinding     `json:"release"`
	PublicationID        string                         `json:"publicationId"`
	SourceSnapshotDigest string                         `json:"sourceSnapshotDigest"`
	CreatorSearchProof   *rt.ReleaseQueryReadinessProof `json:"creatorSearchProof"`
	PostSearchProof      *rt.ReleaseQueryReadinessProof `json:"postSearchProof"`
	HomepageSearchProof  *rt.ReleaseQueryReadinessProof `json:"homepageSearchProof"`
}
type ReleaseQueryPrepareFacade struct {
	sources                 ReleaseSourceQueries
	search                  SearchPreparationPort
	publisher               CandidatePublisher
	environment, generation string
}

func NewReleaseQueryPrepareFacade(sources ReleaseSourceQueries, search SearchPreparationPort, publisher CandidatePublisher, environment, generation string) (*ReleaseQueryPrepareFacade, error) {
	if sources == nil || search == nil || publisher == nil || environment == "" || generation == "" {
		return nil, ErrReleaseQueryNotReady
	}
	return &ReleaseQueryPrepareFacade{sources, search, publisher, environment, generation}, nil
}
func (f *ReleaseQueryPrepareFacade) Prepare(ctx context.Context, c PreparePostReleaseQueriesCommand) (PostReleaseQueryPreparationResult, error) {
	result := PostReleaseQueryPreparationResult{Release: c.PostBinding.Release}
	for n, b := range []rt.ReleaseQueryPreparationBinding{c.CreatorBinding, c.PostBinding, c.HomepageBinding, c.RecommendationBinding} {
		if b.Release != result.Release || b.Validate(f.environment, f.generation) != nil || b.Slice != []string{"creator_search", "post_search", "homepage_search", "recommendation"}[n] {
			return result, ErrReleaseQueryInvalid
		}
	}
	creator, err := f.sources.ReadCreatorCandidate(ctx, result.Release)
	if err != nil {
		return result, err
	}
	post, err := f.sources.ReadPostCandidate(ctx, result.Release)
	if err != nil {
		return result, err
	}
	homepage, err := f.sources.ReadHomepageCandidate(ctx, result.Release)
	if err != nil {
		return result, err
	}
	if creator.Validate() != nil || post.Validate() != nil || homepage.Validate() != nil {
		return result, ErrReleaseQueryInvalid
	}
	publication, err := f.publisher.Publish(ctx, c.RecommendationBinding, post)
	if err != nil {
		return result, err
	}
	result.PublicationID = publication
	result.SourceSnapshotDigest = post.SnapshotDigest
	snapshots := []rt.SearchReleaseCandidateSnapshot{{Kind: "creator", Creator: &creator}, {Kind: "post", Post: &post}, {Kind: "homepage", Homepage: &homepage}}
	bindings := []rt.ReleaseQueryPreparationBinding{c.CreatorBinding, c.PostBinding, c.HomepageBinding}
	versions := []int64{c.ExpectedCreatorPreparationVersion, c.ExpectedPostPreparationVersion, c.ExpectedHomepagePreparationVersion}
	proofs := []**rt.ReleaseQueryReadinessProof{&result.CreatorSearchProof, &result.PostSearchProof, &result.HomepageSearchProof}
	for i, snapshot := range snapshots {
		key, err := rt.CreatorCanonicalDigest([]string{c.IdempotencyKey, bindings[i].ID()}, "")
		if err != nil {
			return result, err
		}
		if err = f.search.PrepareSearchRelease(ctx, bindings[i], snapshot, versions[i], key); err != nil {
			return result, err
		}
		proof, err := f.search.ReadSearchProof(ctx, bindings[i], snapshot.SnapshotDigest())
		if err != nil {
			return result, err
		}
		if proof.Validate(bindings[i], snapshot) != nil {
			return result, ErrReleaseQueryInvalid
		}
		*proofs[i] = &proof
	}
	return result, nil
}
