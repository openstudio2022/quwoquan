package homepage

import (
	"context"
	"fmt"
	rt "quwoquan_service/runtime/search"
)

type HomepageCandidateReader interface {
	ReadHomepageCandidate(context.Context, rt.ReleaseCandidateBinding) (rt.ReleaseHomepageCandidateSnapshot, error)
}
type HomepageReleaseCandidateQueryFacade struct {
	reader      HomepageCandidateReader
	environment string
}

func NewHomepageReleaseCandidateQueryFacade(reader HomepageCandidateReader, environment string) *HomepageReleaseCandidateQueryFacade {
	return &HomepageReleaseCandidateQueryFacade{reader, environment}
}
func (f *HomepageReleaseCandidateQueryFacade) Read(ctx context.Context, b rt.ReleaseCandidateBinding) (rt.ReleaseHomepageCandidateSnapshot, error) {
	if b.Validate() != nil || b.Environment != f.environment {
		return rt.ReleaseHomepageCandidateSnapshot{}, rt.ErrCreatorSourceInvalid
	}
	if f.reader == nil {
		return rt.ReleaseHomepageCandidateSnapshot{}, fmt.Errorf("Homepage reader unavailable")
	}
	return f.reader.ReadHomepageCandidate(ctx, b)
}
