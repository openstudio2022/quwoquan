package creatorsearch

import (
	"context"
	"quwoquan_service/runtime/auth"
	rt "quwoquan_service/runtime/search"
	"time"
)

// Post源只能通过Content本域application调用，Homepage通过正式HTTP。
type PostReader interface {
	ReadPostCandidate(context.Context, rt.ReleaseCandidateBinding) (rt.ReleasePostCandidateSnapshot, error)
}
type Sources struct {
	*Client
	entityURL        string
	entityCredential auth.ServiceAuthorizationProvider
	post             PostReader
}

func NewSources(client *Client, entityURL string, credential auth.ServiceAuthorizationProvider) *Sources {
	return &Sources{Client: client, entityURL: entityURL, entityCredential: credential}
}
func (s *Sources) SetPostReader(reader PostReader) { s.post = reader }
func (s *Sources) ReadPostCandidate(ctx context.Context, b rt.ReleaseCandidateBinding) (rt.ReleasePostCandidateSnapshot, error) {
	return s.post.ReadPostCandidate(ctx, b)
}
func (s *Sources) ReadHomepageCandidate(ctx context.Context, b rt.ReleaseCandidateBinding) (rt.ReleaseHomepageCandidateSnapshot, error) {
	var result rt.ReleaseHomepageCandidateSnapshot
	err := s.call(ctx, s.entityURL, "entity", "entity.homepage.ReadHomepageReleaseCandidate", s.entityCredential, 3*time.Second, struct {
		Release rt.ReleaseCandidateBinding `json:"release"`
	}{b}, &result, "")
	if err != nil {
		return result, err
	}
	return result, result.Validate()
}
