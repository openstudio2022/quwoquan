package post

import (
	"context"

	rtobs "quwoquan_service/runtime/observability"
	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/services/content-service/internal/application/searchprojection"
)

// RetrievePosts runs the unified retrieve contract scoped to content targets.
func (s *PostService) RetrievePosts(
	ctx context.Context,
	req rtsearch.RetrieveRequest,
	viewer rtsearch.Viewer,
) (rtsearch.RetrieveResponse, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "content.RetrievePosts")
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	backend := rtsearch.NewNativeStoreBackend(searchprojection.PostCandidateSource{Reader: s.store})
	return rtsearch.Retrieve(ctx, req, backend, viewer)
}
