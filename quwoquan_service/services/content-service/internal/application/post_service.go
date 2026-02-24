package application

import (
	"context"
	"fmt"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	rtrec "quwoquan_service/runtime/recommendation"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"quwoquan_service/services/content-service/internal/generated"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

type PostService struct {
	store    *persistence.PostStore
	signaler rtrec.SignalProcessor
}

func NewPostService(store *persistence.PostStore, opts ...PostServiceOption) *PostService {
	s := &PostService{store: store}
	for _, opt := range opts {
		opt(s)
	}
	return s
}

type PostServiceOption func(*PostService)

// WithSignalProcessor enables recommendation pipeline notification on post creation.
func WithSignalProcessor(sp rtrec.SignalProcessor) PostServiceOption {
	return func(s *PostService) { s.signaler = sp }
}

func (s *PostService) CreatePost(ctx context.Context, payload map[string]any) (*postmodel.Post, error) {
	contentType := strings.TrimSpace(asString(payload["contentType"]))
	if contentType == "" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "contentType 必填", "missing contentType")
	}
	if _, ok := generated.AllowedContentTypes[contentType]; !ok {
		return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "contentType 不支持", "unsupported contentType")
	}
	now := time.Now().UTC()
	post := &postmodel.Post{
		ID:               fmt.Sprintf("post_%d", now.UnixNano()),
		AuthorId:         strings.TrimSpace(asString(payload["authorId"])),
		PersonaId:        strings.TrimSpace(asString(payload["personaId"])),
		ContentType:      contentType,
		Title:            strings.TrimSpace(asString(payload["title"])),
		Body:             strings.TrimSpace(asString(payload["body"])),
		Tags:             asStringSlice(payload["tags"]),
		MediaUrls:        asStringSlice(payload["mediaUrls"]),
		CoverUrl:         strings.TrimSpace(asString(payload["coverUrl"])),
		VideoUrl:         strings.TrimSpace(asString(payload["videoUrl"])),
		Location:         parseGeoPoint(payload["location"]),
		LocationName:     strings.TrimSpace(asString(payload["locationName"])),
		Visibility:       defaultString(strings.TrimSpace(asString(payload["visibility"])), "public"),
		CircleId:         strings.TrimSpace(asString(payload["circleId"])),
		Status:           "published",
		ModerationStatus: "pending",
		CreatedAt:        now,
		UpdatedAt:        now,
		PublishedAt:      now,
	}
	if post.AuthorId == "" {
		post.AuthorId = "user_guest"
	}
	if err := s.store.Create(ctx, post); err != nil {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "create_failed"),
			"创建内容失败",
			err.Error(),
			true,
		)
	}

	// Notify recommendation pipeline so the new post enters recall immediately
	if s.signaler != nil {
		tags := behaviorTagsFromPost(post)
		_ = s.signaler.ProcessSignal(ctx, rtrec.BehaviorSignal{
			UserID:    post.AuthorId,
			ContentID: post.ID,
			Action:    "impression",
			Tags:      tags,
			Timestamp: now,
		})
	}

	return post, nil
}

func (s *PostService) UpdatePost(ctx context.Context, id string, payload map[string]any) (*postmodel.Post, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(id))
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
			false,
		)
	}
	if title, exists := payload["title"]; exists {
		post.Title = strings.TrimSpace(asString(title))
	}
	if body, exists := payload["body"]; exists {
		post.Body = strings.TrimSpace(asString(body))
	}
	if tags, exists := payload["tags"]; exists {
		post.Tags = asStringSlice(tags)
	}
	if media, exists := payload["mediaUrls"]; exists {
		post.MediaUrls = asStringSlice(media)
	}
	if cover, exists := payload["coverUrl"]; exists {
		post.CoverUrl = strings.TrimSpace(asString(cover))
	}
	if video, exists := payload["videoUrl"]; exists {
		post.VideoUrl = strings.TrimSpace(asString(video))
	}
	if loc, exists := payload["location"]; exists {
		post.Location = parseGeoPoint(loc)
	}
	if locName, exists := payload["locationName"]; exists {
		post.LocationName = strings.TrimSpace(asString(locName))
	}
	post.UpdatedAt = time.Now().UTC()
	if updated := s.store.Update(ctx, post.ID, post); !updated {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "update_failed"),
			"更新内容失败",
			"post disappeared while updating",
			true,
		)
	}
	return post, nil
}

func asString(v any) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}

func asStringSlice(v any) []string {
	switch vv := v.(type) {
	case []string:
		return vv
	case []any:
		out := make([]string, 0, len(vv))
		for _, item := range vv {
			s := strings.TrimSpace(asString(item))
			if s != "" {
				out = append(out, s)
			}
		}
		return out
	default:
		return nil
	}
}

func defaultString(v string, fallback string) string {
	if v == "" {
		return fallback
	}
	return v
}

func parseGeoPoint(v any) postmodel.GeoPoint {
	m, ok := v.(map[string]any)
	if !ok {
		return postmodel.GeoPoint{}
	}
	return postmodel.GeoPoint{
		Latitude:  asFloat64(m["latitude"]),
		Longitude: asFloat64(m["longitude"]),
	}
}

func asFloat64(v any) float64 {
	switch n := v.(type) {
	case float64:
		return n
	case float32:
		return float64(n)
	case int:
		return float64(n)
	case int64:
		return float64(n)
	default:
		return 0
	}
}

func behaviorTagsFromPost(p *postmodel.Post) []string {
	tags := asStringSlice(p.Tags)
	if len(tags) == 0 && p.ContentType != "" {
		tags = []string{p.ContentType}
	}
	return tags
}
