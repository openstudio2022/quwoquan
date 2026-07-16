package searchprojection

import (
	"context"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

type PublishedPostReader interface {
	ListPublished(ctx context.Context, limit int, cursor string) []postmodel.Post
}

// PostCandidateSource adapts the content store into a rtsearch.CandidateSource.
type PostCandidateSource struct {
	Reader PublishedPostReader
}

func (PostCandidateSource) SourceName() string { return "content" }

func (s PostCandidateSource) Candidates(ctx context.Context, plan rtsearch.RetrievePlan) ([]rtsearch.Document, error) {
	if s.Reader == nil || !plan.WantsAny(rtsearch.TargetArticle, rtsearch.TargetPhoto, rtsearch.TargetVideo) {
		return nil, nil
	}
	limit := plan.Limit
	if limit <= 0 {
		limit = 20
	}
	posts := s.Reader.ListPublished(ctx, limit*8, "")
	docs := make([]rtsearch.Document, 0, len(posts))
	for _, stored := range posts {
		docs = append(docs, ProjectPostToSearchDocument(stored))
	}
	return docs, nil
}

// ProjectPostToSearchDocument is the single source of truth for post -> search
// Document mapping, shared by native retrieve and ES indexing.
func ProjectPostToSearchDocument(stored postmodel.Post) rtsearch.Document {
	post := normalizePostForSearchRead(stored)
	summary := strings.TrimSpace(post.Summary)
	if summary == "" {
		summary = strings.TrimSpace(post.Body)
	}
	visibility := strings.TrimSpace(post.Visibility)
	if visibility == "" {
		visibility = "public"
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
		Tags:         stringSlice(post.TagRefs),
		Entities:     stringSlice(post.EntityRefs),
		Popularity:   float64(post.LikeCount + post.CommentCount + post.ShareCount),
		Freshness:    post.PublishedAt,
		Fields: map[string]string{
			"authorId":          post.AuthorId,
			"authorName":        post.AuthorDisplayNameSnapshot,
			"authorDisplayName": post.AuthorDisplayNameSnapshot,
			"placeName":         post.LocationName,
		},
	}
	if post.Location.Latitude != 0 || post.Location.Longitude != 0 {
		doc.Geo = &rtsearch.GeoPoint{Lat: post.Location.Latitude, Lng: post.Location.Longitude}
	}
	return doc
}

func normalizePostForSearchRead(post postmodel.Post) postmodel.Post {
	if strings.TrimSpace(post.ContentIdentity) == "" {
		if strings.TrimSpace(strings.ToLower(post.ContentType)) == "micro" {
			post.ContentIdentity = "moment"
		} else {
			post.ContentIdentity = "work"
		}
	}
	if strings.TrimSpace(post.Visibility) == "" {
		post.Visibility = "public"
	}
	return post
}

func stringSlice(v any) []string {
	switch vv := v.(type) {
	case []string:
		return vv
	case []any:
		out := make([]string, 0, len(vv))
		for _, item := range vv {
			if s, ok := item.(string); ok {
				if trimmed := strings.TrimSpace(s); trimmed != "" {
					out = append(out, trimmed)
				}
			}
		}
		return out
	default:
		return nil
	}
}
