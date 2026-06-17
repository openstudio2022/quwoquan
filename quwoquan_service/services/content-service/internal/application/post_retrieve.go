package application

import (
	"context"
	"strings"

	rtobs "quwoquan_service/runtime/observability"
	rtsearch "quwoquan_service/runtime/search"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
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
		docs = append(docs, ProjectPostToSearchDocument(stored))
	}
	return docs, nil
}

// ProjectPostToSearchDocument projects a stored post into the unified search
// Document carrying the AI target (article/photo/video) and reverse-lookup anchor
// fields. It is the single source of truth for post→Document mapping, shared by
// the native retrieve candidate source (PostCandidateSource) and the ES
// search-index projector so the two never diverge.
func ProjectPostToSearchDocument(stored postmodel.Post) rtsearch.Document {
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
	doc := rtsearch.Document{
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
		Popularity:   float64(post.LikeCount + post.CommentCount + post.ShareCount),
		Freshness:    post.PublishedAt,
		Fields: map[string]string{
			"authorId":          post.AuthorId,
			"authorName":        post.AuthorDisplayNameSnapshot,
			"authorDisplayName": post.AuthorDisplayNameSnapshot,
			// placeName is the cross-object location dimension (R-S05e); a post's
			// LocationName is the place it was published at.
			"placeName": post.LocationName,
			"circleId":  primaryCircleID,
		},
	}
	// Geo comes from the post's real location coordinates (never fabricated):
	// only set when a non-zero coordinate was captured, so "附近的内容" works.
	if post.Location.Latitude != 0 || post.Location.Longitude != 0 {
		doc.Geo = &rtsearch.GeoPoint{Lat: post.Location.Latitude, Lng: post.Location.Longitude}
	}
	return doc
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
