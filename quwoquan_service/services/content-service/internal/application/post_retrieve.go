package application

import (
	"context"
	"strings"

	rtobs "quwoquan_service/runtime/observability"
	rtsearch "quwoquan_service/runtime/search"
)

// PostCandidateSource adapts the content store into a rtsearch.CandidateSource
// so the content provider participates in the unified retrieve contract via the
// NativeStoreBackend (Mongo text / receipted query today, ES later — transparent).
type PostCandidateSource struct {
	reader publishedPostReader
}

// SourceName implements rtsearch.CandidateSource.
func (PostCandidateSource) SourceName() string { return "content" }

// Candidates implements rtsearch.CandidateSource. It pushes the planned limit
// down to the store and projects published posts into search Documents tagged
// with the AI target (article/photo/video) and reverse-lookup anchor fields.
func (s PostCandidateSource) Candidates(ctx context.Context, plan rtsearch.RetrievePlan) ([]rtsearch.Document, error) {
	if !plan.WantsAny(rtsearch.TargetArticle, rtsearch.TargetPhoto, rtsearch.TargetVideo) {
		return nil, nil
	}
	limit := plan.Limit
	if limit <= 0 {
		limit = 20
	}
	posts := s.reader.ListPublished(ctx, limit*8, "")
	docs := make([]rtsearch.Document, 0, len(posts))
	for _, stored := range posts {
		post := *normalizePostForRead(&stored)
		summary := strings.TrimSpace(post.Summary)
		if summary == "" {
			summary = strings.TrimSpace(post.Body)
		}
		visibility := strings.TrimSpace(post.Visibility)
		if visibility == "" {
			visibility = "public"
		}
		primaryCircleID := strings.TrimSpace(post.CircleId)
		if primaryCircleID == "" {
			if ids := asStringSlice(post.CircleIds); len(ids) > 0 {
				primaryCircleID = strings.TrimSpace(ids[0])
			}
		}
		docs = append(docs, rtsearch.Document{
			ObjectType:   rtsearch.ObjectTypeContentPost,
			ObjectID:     post.ID,
			Title:        post.Title,
			Summary:      summary,
			Body:         post.Body,
			SourceDomain: "content",
			ContentType:  post.ContentType,
			Visibility:   visibility,
			BadgeLabel:   "内容",
			Tags:         asStringSlice(post.TagRefs),
			Entities:     asStringSlice(post.EntityRefs),
			Popularity:   float64(post.LikeCount + post.CommentCount + post.FavoriteCount + post.ShareCount),
			Freshness:    post.PublishedAt,
			Fields: map[string]string{
				"authorId":          post.AuthorId,
				"authorName":        post.AuthorDisplayNameSnapshot,
				"authorDisplayName": post.AuthorDisplayNameSnapshot,
				"locationName":      post.LocationName,
				"circleId":          primaryCircleID,
			},
		})
	}
	return docs, nil
}

// RetrievePosts runs the unified retrieve contract scoped to content targets,
// returning standard retrieve hits. It is the content provider's entry into the
// cross-type retrieve pipeline.
func (s *PostService) RetrievePosts(
	ctx context.Context,
	req rtsearch.RetrieveRequest,
	viewer rtsearch.Viewer,
) (rtsearch.RetrieveResponse, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "content.RetrievePosts")
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	backend := rtsearch.NewNativeStoreBackend(PostCandidateSource{reader: s.store})
	var resp rtsearch.RetrieveResponse
	resp, err = rtsearch.Retrieve(ctx, req, backend, viewer)
	return resp, err
}
