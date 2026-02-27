package application

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/repository"
	rtrec "quwoquan_service/runtime/recommendation"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"quwoquan_service/services/content-service/internal/generated"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

type PostService struct {
	store     persistence.PostRepository
	signaler  rtrec.SignalProcessor
	publisher repository.EventPublisher
	mu        sync.Mutex
	reactions map[string]map[string]contentReactionState // postID -> userID -> state
}

func NewPostService(store persistence.PostRepository, opts ...PostServiceOption) *PostService {
	s := &PostService{
		store:     store,
		reactions: map[string]map[string]contentReactionState{},
	}
	for _, opt := range opts {
		opt(s)
	}
	return s
}

type contentReactionState struct {
	Liked     bool
	Favorited bool
}

type PostServiceOption func(*PostService)

// WithSignalProcessor enables recommendation pipeline notification on post creation.
func WithSignalProcessor(sp rtrec.SignalProcessor) PostServiceOption {
	return func(s *PostService) { s.signaler = sp }
}

// WithEventPublisher enables domain event publishing (e.g. PostCreated).
func WithEventPublisher(pub repository.EventPublisher) PostServiceOption {
	return func(s *PostService) { s.publisher = pub }
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

	// Notify recommendation pipeline so the new post enters recall immediately.
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

	// Publish PostCreated domain event for downstream consumers.
	if s.publisher != nil {
		_ = s.publisher.Publish(ctx, repository.DomainEvent{
			Type:          "PostCreated",
			AggregateType: "Post",
			AggregateID:   post.ID,
			Payload: map[string]any{
				"authorId":    post.AuthorId,
				"contentType": post.ContentType,
			},
			OccurredAt: now.Format(time.RFC3339),
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

func (s *PostService) LikePost(ctx context.Context, postID, userID string) (int64, bool, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return 0, false, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
			false,
		)
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		userID = "guest"
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	byPost, ok := s.reactions[post.ID]
	if !ok {
		byPost = map[string]contentReactionState{}
		s.reactions[post.ID] = byPost
	}
	state := byPost[userID]
	changed := !state.Liked
	if changed {
		state.Liked = true
		byPost[userID] = state
		post.LikeCount++
		post.UpdatedAt = time.Now().UTC()
		_ = s.store.Update(ctx, post.ID, post)
	}
	return post.LikeCount, changed, nil
}

func (s *PostService) UnlikePost(ctx context.Context, postID, userID string) (int64, bool, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return 0, false, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
			false,
		)
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		userID = "guest"
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	byPost, ok := s.reactions[post.ID]
	if !ok {
		byPost = map[string]contentReactionState{}
		s.reactions[post.ID] = byPost
	}
	state := byPost[userID]
	changed := state.Liked
	if changed {
		state.Liked = false
		byPost[userID] = state
		if post.LikeCount > 0 {
			post.LikeCount--
		}
		post.UpdatedAt = time.Now().UTC()
		_ = s.store.Update(ctx, post.ID, post)
	}
	return post.LikeCount, changed, nil
}

func (s *PostService) FavoritePost(ctx context.Context, postID, userID string) (int64, bool, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return 0, false, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
			false,
		)
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		userID = "guest"
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	byPost, ok := s.reactions[post.ID]
	if !ok {
		byPost = map[string]contentReactionState{}
		s.reactions[post.ID] = byPost
	}
	state := byPost[userID]
	changed := !state.Favorited
	if changed {
		state.Favorited = true
		byPost[userID] = state
		post.FavoriteCount++
		post.UpdatedAt = time.Now().UTC()
		_ = s.store.Update(ctx, post.ID, post)
	}
	return post.FavoriteCount, changed, nil
}

func (s *PostService) UnfavoritePost(ctx context.Context, postID, userID string) (int64, bool, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return 0, false, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
			false,
		)
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		userID = "guest"
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	byPost, ok := s.reactions[post.ID]
	if !ok {
		byPost = map[string]contentReactionState{}
		s.reactions[post.ID] = byPost
	}
	state := byPost[userID]
	changed := state.Favorited
	if changed {
		state.Favorited = false
		byPost[userID] = state
		if post.FavoriteCount > 0 {
			post.FavoriteCount--
		}
		post.UpdatedAt = time.Now().UTC()
		_ = s.store.Update(ctx, post.ID, post)
	}
	return post.FavoriteCount, changed, nil
}

func (s *PostService) GetReactionState(postID, userID string) (liked, favorited bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	byPost, ok := s.reactions[strings.TrimSpace(postID)]
	if !ok {
		return false, false
	}
	state, ok := byPost[strings.TrimSpace(userID)]
	if !ok {
		return false, false
	}
	return state.Liked, state.Favorited
}

func (s *PostService) AddComment(ctx context.Context, postID, userID, content, replyToCommentID string) (map[string]any, int64, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return nil, 0, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
			false,
		)
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		userID = "guest"
	}
	content = strings.TrimSpace(content)
	if content == "" {
		return nil, 0, rterr.NewInvalidArgument(rterr.ModuleContent, "评论内容不能为空", "empty comment content")
	}
	now := time.Now().UTC()
	post.CommentCount++
	post.UpdatedAt = now
	_ = s.store.Update(ctx, post.ID, post)
	comment := map[string]any{
		"_id":              fmt.Sprintf("comment_%d", now.UnixNano()),
		"postId":           post.ID,
		"authorId":         userID,
		"content":          content,
		"replyToCommentId": strings.TrimSpace(replyToCommentID),
		"createdAt":        now.Format(time.RFC3339),
	}
	return comment, post.CommentCount, nil
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
