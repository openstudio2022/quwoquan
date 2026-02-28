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
	distributions map[string]map[string]bool             // postID -> circleID -> active
	reshares      map[string]map[string]bool             // postID -> (circleID:userID) -> active
	tombstones    map[string]time.Time                   // postID -> deletedAt
	mediaAssets   map[string]postmodel.MediaAsset        // mediaID -> asset
	uploadSession map[string]string                      // sessionID -> mediaID
}

func NewPostService(store persistence.PostRepository, opts ...PostServiceOption) *PostService {
	s := &PostService{
		store:         store,
		reactions:     map[string]map[string]contentReactionState{},
		distributions: map[string]map[string]bool{},
		reshares:      map[string]map[string]bool{},
		tombstones:    map[string]time.Time{},
		mediaAssets:   map[string]postmodel.MediaAsset{},
		uploadSession: map[string]string{},
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
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "invalid_content_type"),
			"contentType 不支持",
			"unsupported contentType",
			false,
		)
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
		CircleIds:        asStringSlice(payload["circleIds"]),
		SourcePostId:     strings.TrimSpace(asString(payload["sourcePostId"])),
		SourceType:       defaultString(strings.TrimSpace(asString(payload["sourceType"])), "original"),
		Summary:          strings.TrimSpace(asString(payload["summary"])),
		IllustrationAssetId: strings.TrimSpace(asString(payload["illustrationAssetId"])),
		PublishLocation:  asMap(payload["publishLocation"]),
		DeviceInfo:       asMap(payload["deviceInfo"]),
		Status:           "published",
		ModerationStatus: "pending",
		CreatedAt:        now,
		UpdatedAt:        now,
		PublishedAt:      now,
	}
	if post.AuthorId == "" {
		post.AuthorId = "user_guest"
	}
	if post.SourceType == "" {
		post.SourceType = "original"
	}
	if err := validateCreatePostPayload(post); err != nil {
		return nil, err
	}
	if err := s.store.Create(ctx, post); err != nil {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "create_failed"),
			"创建内容失败",
			err.Error(),
			true,
		)
	}
	s.mu.Lock()
	if circles := asStringSlice(post.CircleIds); len(circles) > 0 {
		if _, ok := s.distributions[post.ID]; !ok {
			s.distributions[post.ID] = map[string]bool{}
		}
		for _, circleID := range circles {
			if circleID != "" {
				s.distributions[post.ID][circleID] = true
			}
		}
	}
	s.mu.Unlock()

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
	if strings.EqualFold(strings.TrimSpace(post.Status), "published") {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "conflict"),
			"内容发布后不可修改",
			"post immutable after publish",
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

func (s *PostService) PublishPost(ctx context.Context, postID string) (*postmodel.Post, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
			false,
		)
	}
	if strings.EqualFold(post.Status, "deleted") {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "conflict"),
			"内容已删除",
			"post deleted",
			false,
		)
	}
	if strings.EqualFold(post.Status, "published") {
		return post, nil
	}
	post.Status = "published"
	post.PublishedAt = time.Now().UTC()
	post.UpdatedAt = post.PublishedAt
	if !s.store.Update(ctx, post.ID, post) {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "internal_error"),
			"发布失败",
			"update failed",
			true,
		)
	}
	return post, nil
}

func (s *PostService) DeletePost(ctx context.Context, postID, userID string) error {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
			false,
		)
	}
	if userID != "" && post.AuthorId != "" && post.AuthorId != userID {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "forbidden"),
			"无权删除此内容",
			"author mismatch",
			false,
		)
	}
	now := time.Now().UTC()
	post.Status = "deleted"
	post.DeletedAt = now
	post.UpdatedAt = now
	_ = s.store.Update(ctx, post.ID, post)
	s.mu.Lock()
	s.tombstones[post.ID] = now
	delete(s.distributions, post.ID)
	delete(s.reshares, post.ID)
	s.mu.Unlock()
	return nil
}

func (s *PostService) UpdatePostCircles(ctx context.Context, postID, userID string, add, remove []string) (map[string]any, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
			false,
		)
	}
	if post.AuthorId != "" && userID != "" && post.AuthorId != userID {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "forbidden"),
			"无权修改圈子分发关系",
			"author mismatch",
			false,
		)
	}
	if strings.TrimSpace(strings.ToLower(post.Visibility)) != "public" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "发布到圈子前需设置为公开", "visibility must be public")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	byPost, ok := s.distributions[post.ID]
	if !ok {
		byPost = map[string]bool{}
		s.distributions[post.ID] = byPost
	}
	for _, circleID := range add {
		if cid := strings.TrimSpace(circleID); cid != "" {
			byPost[cid] = true
		}
	}
	for _, circleID := range remove {
		delete(byPost, strings.TrimSpace(circleID))
	}
	active := make([]string, 0, len(byPost))
	for cid, on := range byPost {
		if on {
			active = append(active, cid)
		}
	}
	post.CircleIds = active
	post.UpdatedAt = time.Now().UTC()
	_ = s.store.Update(ctx, post.ID, post)
	return map[string]any{
		"postId":    post.ID,
		"circleIds": active,
	}, nil
}

func (s *PostService) RepostToCircle(ctx context.Context, postID, userID, circleID, quote string) (map[string]any, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
			false,
		)
	}
	if strings.EqualFold(post.Status, "deleted") {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "conflict"),
			"内容已删除",
			"post deleted",
			false,
		)
	}
	if strings.TrimSpace(strings.ToLower(post.Visibility)) != "public" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "发布到圈子前需设置为公开", "visibility must be public")
	}
	circleID = strings.TrimSpace(circleID)
	if circleID == "" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "圈子不能为空", "missing circleId")
	}
	if userID == "" {
		userID = "guest"
	}
	key := circleID + ":" + userID
	s.mu.Lock()
	if _, ok := s.reshares[post.ID]; !ok {
		s.reshares[post.ID] = map[string]bool{}
	}
	s.reshares[post.ID][key] = true
	s.mu.Unlock()
	return map[string]any{
		"postId":         post.ID,
		"sourcePostId":   post.ID,
		"resharerUserId": userID,
		"circleId":       circleID,
		"quoteText":      strings.TrimSpace(quote),
		"type":           "moment",
	}, nil
}

func (s *PostService) InitMediaUpload(_ context.Context, userID, mediaType string) map[string]any {
	now := time.Now().UTC()
	if userID == "" {
		userID = "guest"
	}
	mediaID := fmt.Sprintf("media_%d", now.UnixNano())
	sessionID := fmt.Sprintf("upload_%d", now.UnixNano())
	asset := postmodel.MediaAsset{
		ID:               mediaID,
		Type:             defaultString(strings.TrimSpace(mediaType), "image"),
		Status:           "uploaded",
		CoverStrategy:    "first_frame",
		ModerationStatus: "pending",
		CreatedAt:        now,
		UpdatedAt:        now,
	}
	s.mu.Lock()
	s.mediaAssets[mediaID] = asset
	s.uploadSession[sessionID] = mediaID
	s.mu.Unlock()
	return map[string]any{
		"sessionId":  sessionID,
		"mediaId":    mediaID,
		"uploadUrl":  "https://origin.example/upload/" + mediaID,
		"uploaderId": userID,
	}
}

func (s *PostService) CompleteMediaUpload(_ context.Context, sessionID string) (*postmodel.MediaAsset, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	mediaID := s.uploadSession[strings.TrimSpace(sessionID)]
	if mediaID == "" {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"上传会话不存在",
			"upload session not found",
			false,
		)
	}
	asset, ok := s.mediaAssets[mediaID]
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"媒体不存在",
			"media not found",
			false,
		)
	}
	asset.Status = "ready"
	asset.CdnUrl = "https://cdn.example/media/" + mediaID
	asset.ThumbnailUrl = "https://cdn.example/media/" + mediaID + "/thumb.jpg"
	if asset.Type == "video" {
		asset.DurationMs = 15000
		asset.Width = 1080
		asset.Height = 1920
		asset.FileSizeBytes = 5 * 1024 * 1024
	} else {
		asset.Width = 1080
		asset.Height = 1080
		asset.FileSizeBytes = 500 * 1024
	}
	asset.UpdatedAt = time.Now().UTC()
	s.mediaAssets[mediaID] = asset
	return &asset, nil
}

func (s *PostService) AbortMediaUpload(_ context.Context, sessionID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.uploadSession, strings.TrimSpace(sessionID))
	return nil
}

func (s *PostService) GetMediaAsset(mediaID string) (*postmodel.MediaAsset, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	asset, ok := s.mediaAssets[strings.TrimSpace(mediaID)]
	if !ok {
		return nil, false
	}
	cp := asset
	return &cp, true
}

func (s *PostService) SelectAutoVideoCover(_ context.Context, mediaID string) (*postmodel.MediaAsset, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	asset, ok := s.mediaAssets[strings.TrimSpace(mediaID)]
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"媒体不存在",
			"media not found",
			false,
		)
	}
	asset.CoverStrategy = "first_frame"
	asset.ManualCoverAssetId = ""
	asset.UpdatedAt = time.Now().UTC()
	s.mediaAssets[asset.ID] = asset
	cp := asset
	return &cp, nil
}

func (s *PostService) SelectManualVideoCover(_ context.Context, mediaID, coverAssetID string) (*postmodel.MediaAsset, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	asset, ok := s.mediaAssets[strings.TrimSpace(mediaID)]
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"媒体不存在",
			"media not found",
			false,
		)
	}
	asset.CoverStrategy = "manual"
	asset.ManualCoverAssetId = strings.TrimSpace(coverAssetID)
	asset.UpdatedAt = time.Now().UTC()
	s.mediaAssets[asset.ID] = asset
	cp := asset
	return &cp, nil
}

func (s *PostService) GenerateArticleSummary(title, body string) string {
	t := strings.TrimSpace(title)
	b := strings.TrimSpace(body)
	if b == "" {
		return t
	}
	if len(b) > 100 {
		b = b[:100]
	}
	if t == "" {
		return b
	}
	return t + "：" + b
}

func (s *PostService) GetPostOrTombstone(ctx context.Context, postID string) (*postmodel.Post, bool, bool) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if ok && !strings.EqualFold(strings.TrimSpace(post.Status), "deleted") {
		return post, true, false
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	_, deleted := s.tombstones[strings.TrimSpace(postID)]
	return nil, false, deleted
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

func asMap(v any) map[string]any {
	if m, ok := v.(map[string]any); ok {
		return m
	}
	return nil
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

func validateCreatePostPayload(post *postmodel.Post) error {
	switch strings.TrimSpace(post.ContentType) {
	case "micro":
		hasBody := strings.TrimSpace(post.Body) != ""
		hasImages := len(asStringSlice(post.MediaUrls)) > 0
		hasVideo := strings.TrimSpace(post.VideoUrl) != ""
		if !hasBody && !hasImages && !hasVideo {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "微趣内容不能为空", "moment requires body/image/video at least one")
		}
	case "image":
		if len(asStringSlice(post.MediaUrls)) == 0 {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "美图至少需要一张图片", "photo requires mediaUrls")
		}
	case "video":
		if strings.TrimSpace(post.VideoUrl) == "" {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "视频地址不能为空", "video requires videoUrl")
		}
	case "article":
		if strings.TrimSpace(post.Title) == "" {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "文章标题必填", "article requires title")
		}
	}
	if circles := asStringSlice(post.CircleIds); len(circles) > 0 && strings.TrimSpace(strings.ToLower(post.Visibility)) != "public" {
		return rterr.NewInvalidArgument(rterr.ModuleContent, "发布到圈子前需设置为公开", "visibility must be public")
	}
	return nil
}
