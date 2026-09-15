package application

import (
	"context"
	rt "quwoquan_service/runtime/search"
)

// 唯一候选投影port：不把projection暴露成业务command。
type ReleaseCandidateIndex interface {
	Write(context.Context, rt.ReleaseQueryPreparationBinding, rt.SearchReleaseCandidateSnapshot) ([]string, error)
	Verify(context.Context, rt.ReleaseQueryPreparationBinding, rt.SearchReleaseCandidateSnapshot) ([]rt.ReleaseQueryClassEvidence, error)
}
type ReleaseCandidateProjector struct{ index ReleaseCandidateIndex }

func NewReleaseCandidateProjector(index ReleaseCandidateIndex) *ReleaseCandidateProjector {
	return &ReleaseCandidateProjector{index: index}
}
func (p *ReleaseCandidateProjector) Prepare(ctx context.Context, b rt.ReleaseQueryPreparationBinding, s rt.SearchReleaseCandidateSnapshot) ([]string, error) {
	if err := s.Validate(); err != nil {
		return nil, err
	}
	return p.index.Write(ctx, b, s)
}
func (p *ReleaseCandidateProjector) Verify(ctx context.Context, b rt.ReleaseQueryPreparationBinding, s rt.SearchReleaseCandidateSnapshot) ([]rt.ReleaseQueryClassEvidence, error) {
	return p.index.Verify(ctx, b, s)
}
