package application

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	rterr "quwoquan_service/runtime/errors"
	rtrec "quwoquan_service/runtime/recommendation"
	"quwoquan_service/runtime/repository"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"quwoquan_service/services/content-service/internal/generated"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

// Projector receives domain events for in-process read-model projection.
type Projector interface {
	Project(ctx context.Context, event ProjectorEvent) error
}

type ProjectorEvent struct {
	Type          string         `json:"type"`
	AggregateType string         `json:"aggregateType"`
	AggregateID   string         `json:"aggregateId"`
	Payload       map[string]any `json:"payload"`
	OccurredAt    time.Time      `json:"occurredAt"`
}

type ProjectionRebuildReport struct {
	DryRun                       bool `json:"dryRun"`
	TotalPosts                   int  `json:"totalPosts"`
	DraftPosts                   int  `json:"draftPosts"`
	PublishedPosts               int  `json:"publishedPosts"`
	DeletedPosts                 int  `json:"deletedPosts"`
	PublicPosts                  int  `json:"publicPosts"`
	PrivatePosts                 int  `json:"privatePosts"`
	CircleVisiblePosts           int  `json:"circleVisiblePosts"`
	AssistantExcludedPosts       int  `json:"assistantExcludedPosts"`
	BackfilledContentIdentity    int  `json:"backfilledContentIdentity"`
	BackfilledAssistantUsePolicy int  `json:"backfilledAssistantUsePolicy"`
	DiscoveryEligiblePosts       int  `json:"discoveryEligiblePosts"`
	DiscoveryRevokedPosts        int  `json:"discoveryRevokedPosts"`
}

type StoryCanaryStage struct {
	Stage          string `json:"stage"`
	RolloutPercent int    `json:"rolloutPercent"`
}

type StoryRuntimeConfig struct {
	FeatureFlags     map[string]bool    `json:"featureFlags"`
	ExperimentBucket string             `json:"experimentBucket"`
	CurrentStage     string             `json:"currentStage"`
	CanaryMatrix     []StoryCanaryStage `json:"canaryMatrix"`
}

type PostService struct {
	store         persistence.PostRepository
	signaler      rtrec.SignalProcessor
	publisher     repository.EventPublisher
	projector     Projector
	logger        *slog.Logger
	mu            sync.Mutex
	reactions     map[string]map[string]contentReactionState // postID -> userID -> state
	distributions map[string]map[string]bool                 // postID -> circleID -> active
	reshares      map[string]map[string]bool                 // postID -> (circleID:userID) -> active
	tombstones    map[string]time.Time                       // postID -> deletedAt
	mediaAssets   map[string]postmodel.MediaAsset            // mediaID -> asset
	uploadSession map[string]string                          // sessionID -> mediaID
	comments      map[string][]map[string]any                // postID -> comments list
	commentLikes  map[string]map[string]bool                 // commentID -> userID -> liked
	commentMaxLen int                                        // configurable, default 500
	storyRuntime  StoryRuntimeConfig
}

func NewPostService(store persistence.PostRepository, opts ...PostServiceOption) *PostService {
	s := &PostService{
		store:         store,
		logger:        slog.Default(),
		reactions:     map[string]map[string]contentReactionState{},
		distributions: map[string]map[string]bool{},
		reshares:      map[string]map[string]bool{},
		tombstones:    map[string]time.Time{},
		mediaAssets:   map[string]postmodel.MediaAsset{},
		uploadSession: map[string]string{},
		comments:      map[string][]map[string]any{},
		commentLikes:  map[string]map[string]bool{},
		commentMaxLen: 500,
		storyRuntime:  defaultStoryRuntimeConfig(),
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

// WithProjector enables in-process read-model projection after writes.
func WithProjector(p Projector) PostServiceOption {
	return func(s *PostService) { s.projector = p }
}

// WithLogger sets a structured logger.
func WithLogger(l *slog.Logger) PostServiceOption {
	return func(s *PostService) { s.logger = l }
}

func WithStoryRuntimeConfig(cfg StoryRuntimeConfig) PostServiceOption {
	return func(s *PostService) {
		s.storyRuntime = normalizeStoryRuntimeConfig(cfg)
	}
}

func defaultStoryRuntimeConfig() StoryRuntimeConfig {
	return StoryRuntimeConfig{
		FeatureFlags: map[string]bool{
			"enable_create_action_entry":              true,
			"enable_unified_create_editor":            true,
			"enable_identity_based_surfaces":          true,
			"enable_identity_share_template":          true,
			"enable_assistant_content_identity_index": true,
		},
		ExperimentBucket: "local_story_enabled",
		CurrentStage:     "100%",
		CanaryMatrix: []StoryCanaryStage{
			{Stage: "5%", RolloutPercent: 5},
			{Stage: "20%", RolloutPercent: 20},
			{Stage: "50%", RolloutPercent: 50},
			{Stage: "100%", RolloutPercent: 100},
		},
	}
}

func normalizeStoryRuntimeConfig(cfg StoryRuntimeConfig) StoryRuntimeConfig {
	fallback := defaultStoryRuntimeConfig()
	normalized := StoryRuntimeConfig{
		FeatureFlags:     map[string]bool{},
		ExperimentBucket: strings.TrimSpace(cfg.ExperimentBucket),
		CurrentStage:     strings.TrimSpace(cfg.CurrentStage),
		CanaryMatrix:     cfg.CanaryMatrix,
	}
	for key, fallbackValue := range fallback.FeatureFlags {
		normalized.FeatureFlags[key] = fallbackValue
	}
	for key, value := range cfg.FeatureFlags {
		normalized.FeatureFlags[key] = value
	}
	if normalized.ExperimentBucket == "" {
		normalized.ExperimentBucket = fallback.ExperimentBucket
	}
	if normalized.CurrentStage == "" {
		normalized.CurrentStage = fallback.CurrentStage
	}
	if len(normalized.CanaryMatrix) == 0 {
		normalized.CanaryMatrix = fallback.CanaryMatrix
	}
	return normalized
}

func (s *PostService) publishPostEvent(
	ctx context.Context,
	eventType string,
	post *postmodel.Post,
	payload map[string]any,
	occurredAt time.Time,
) {
	if s.publisher == nil || post == nil {
		return
	}
	_ = s.publisher.Publish(ctx, repository.DomainEvent{
		Type:          eventType,
		AggregateType: "Post",
		AggregateID:   post.ID,
		Payload:       payload,
		OccurredAt:    occurredAt.Format(time.RFC3339),
	})
}

func (s *PostService) projectPostEvent(
	ctx context.Context,
	eventType string,
	post *postmodel.Post,
	payload map[string]any,
	occurredAt time.Time,
) {
	if s.projector == nil || post == nil {
		return
	}
	projErr := s.projector.Project(ctx, ProjectorEvent{
		Type:          eventType,
		AggregateType: "Post",
		AggregateID:   post.ID,
		Payload:       payload,
		OccurredAt:    occurredAt,
	})
	if projErr != nil {
		s.logger.Warn("projector failed after post event", "type", eventType, "postId", post.ID, "err", projErr)
	}
}

func (s *PostService) syncDistributionsFromPost(post *postmodel.Post) {
	if post == nil {
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	circleIDs := asStringSlice(post.CircleIds)
	if len(circleIDs) == 0 {
		delete(s.distributions, post.ID)
		return
	}
	byPost := map[string]bool{}
	for _, circleID := range circleIDs {
		if cid := strings.TrimSpace(circleID); cid != "" {
			byPost[cid] = true
		}
	}
	if len(byPost) == 0 {
		delete(s.distributions, post.ID)
		return
	}
	s.distributions[post.ID] = byPost
}

func normalizePostForRead(post *postmodel.Post) *postmodel.Post {
	if post == nil {
		return nil
	}
	copy := *post
	if strings.TrimSpace(copy.ContentIdentity) == "" {
		copy.ContentIdentity = normalizeContentIdentity(copy.ContentType, "")
	}
	if strings.TrimSpace(copy.AssistantUsePolicy) == "" {
		copy.AssistantUsePolicy = "inherit"
	}
	copy.Visibility = normalizeVisibility(copy.Visibility)
	return &copy
}

func canViewPost(post *postmodel.Post, viewerID string, viewerCircleIDs []string) bool {
	if post == nil {
		return false
	}
	viewerID = strings.TrimSpace(viewerID)
	if !strings.EqualFold(strings.TrimSpace(post.Status), "published") {
		return viewerID != "" && viewerID == strings.TrimSpace(post.AuthorId)
	}
	visibility := normalizeVisibility(post.Visibility)
	switch visibility {
	case "public":
		return true
	case "circle_visible":
		if viewerID != "" && viewerID == strings.TrimSpace(post.AuthorId) {
			return true
		}
		return sharesCircle(asStringSlice(post.CircleIds), viewerCircleIDs)
	default:
		return viewerID != "" && viewerID == strings.TrimSpace(post.AuthorId)
	}
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
	contentIdentity := normalizeContentIdentity(
		contentType,
		strings.TrimSpace(asString(payload["contentIdentity"])),
	)
	assistantUsePolicy := normalizeAssistantUsePolicy(
		strings.TrimSpace(asString(payload["assistantUsePolicy"])),
	)
	post := &postmodel.Post{
		ID:                  fmt.Sprintf("post_%d", now.UnixNano()),
		AuthorId:            strings.TrimSpace(asString(payload["authorId"])),
		PersonaId:           strings.TrimSpace(asString(payload["personaId"])),
		ContentType:         contentType,
		ContentIdentity:     contentIdentity,
		Title:               strings.TrimSpace(asString(payload["title"])),
		Body:                strings.TrimSpace(asString(payload["body"])),
		Tags:                asStringSlice(payload["tags"]),
		MediaUrls:           asStringSlice(payload["mediaUrls"]),
		CoverUrl:            strings.TrimSpace(asString(payload["coverUrl"])),
		VideoUrl:            strings.TrimSpace(asString(payload["videoUrl"])),
		Location:            parseGeoPoint(payload["location"]),
		LocationName:        strings.TrimSpace(asString(payload["locationName"])),
		Visibility:          normalizeVisibility(asString(payload["visibility"])),
		AssistantUsePolicy:  assistantUsePolicy,
		CircleId:            strings.TrimSpace(asString(payload["circleId"])),
		CircleIds:           asStringSlice(payload["circleIds"]),
		SourcePostId:        strings.TrimSpace(asString(payload["sourcePostId"])),
		SourceType:          defaultString(strings.TrimSpace(asString(payload["sourceType"])), "original"),
		Summary:             strings.TrimSpace(asString(payload["summary"])),
		IllustrationAssetId: strings.TrimSpace(asString(payload["illustrationAssetId"])),
		PublishLocation:     asMap(payload["publishLocation"]),
		DeviceInfo:          asMap(payload["deviceInfo"]),
		Status:              "draft",
		ModerationStatus:    "pending",
		CreatedAt:           now,
		UpdatedAt:           now,
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

	// Publish PostCreated domain event for downstream consumers.
	if s.publisher != nil {
		_ = s.publisher.Publish(ctx, repository.DomainEvent{
			Type:          "PostCreated",
			AggregateType: "Post",
			AggregateID:   post.ID,
			Payload: map[string]any{
				"authorId":           post.AuthorId,
				"contentType":        post.ContentType,
				"contentIdentity":    post.ContentIdentity,
				"status":             post.Status,
				"visibility":         post.Visibility,
				"circleIds":          asStringSlice(post.CircleIds),
				"assistantUsePolicy": post.AssistantUsePolicy,
			},
			OccurredAt: now.Format(time.RFC3339),
		})
	}

	// Synchronous projection for DiscoveryFeed read model.
	if s.projector != nil {
		projErr := s.projector.Project(ctx, ProjectorEvent{
			Type:          "PostCreated",
			AggregateType: "Post",
			AggregateID:   post.ID,
			Payload: map[string]any{
				"_id":                post.ID,
				"authorId":           post.AuthorId,
				"contentType":        post.ContentType,
				"contentIdentity":    post.ContentIdentity,
				"status":             post.Status,
				"visibility":         post.Visibility,
				"assistantUsePolicy": post.AssistantUsePolicy,
				"circleIds":          asStringSlice(post.CircleIds),
				"title":              post.Title,
				"tags":               post.Tags,
				"coverUrl":           post.CoverUrl,
			},
			OccurredAt: now,
		})
		if projErr != nil {
			s.logger.Warn("projector failed after CreatePost", "postId", post.ID, "err", projErr)
		}
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
	if contentType, exists := payload["contentType"]; exists {
		post.ContentType = strings.TrimSpace(asString(contentType))
	}
	if contentIdentity, exists := payload["contentIdentity"]; exists {
		post.ContentIdentity = normalizeContentIdentity(
			post.ContentType,
			strings.TrimSpace(asString(contentIdentity)),
		)
	}
	if body, exists := payload["body"]; exists {
		post.Body = strings.TrimSpace(asString(body))
	}
	if summary, exists := payload["summary"]; exists {
		post.Summary = strings.TrimSpace(asString(summary))
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
	if visibility, exists := payload["visibility"]; exists {
		post.Visibility = normalizeVisibility(asString(visibility))
	}
	if circles, exists := payload["circleIds"]; exists {
		post.CircleIds = asStringSlice(circles)
	}
	if assistantUsePolicy, exists := payload["assistantUsePolicy"]; exists {
		post.AssistantUsePolicy = normalizeAssistantUsePolicy(
			strings.TrimSpace(asString(assistantUsePolicy)),
		)
	}
	if illustrationAssetID, exists := payload["illustrationAssetId"]; exists {
		post.IllustrationAssetId = strings.TrimSpace(asString(illustrationAssetID))
	}
	post.UpdatedAt = time.Now().UTC()
	if err := validateCreatePostPayload(post); err != nil {
		return nil, err
	}
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

func (s *PostService) PublishPost(ctx context.Context, postID string, payload map[string]any) (*postmodel.Post, error) {
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
	if err := applyPostSettingsPayload(post, payload); err != nil {
		return nil, err
	}
	now := time.Now().UTC()
	post.Status = "published"
	if post.PublishedAt.IsZero() {
		post.PublishedAt = now
	}
	post.UpdatedAt = now
	if !s.store.Update(ctx, post.ID, post) {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "internal_error"),
			"发布失败",
			"update failed",
			true,
		)
	}
	s.syncDistributionsFromPost(post)
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
	if s.publisher != nil {
		_ = s.publisher.Publish(ctx, repository.DomainEvent{
			Type:          "PostPublished",
			AggregateType: "Post",
			AggregateID:   post.ID,
			Payload: map[string]any{
				"_id":                post.ID,
				"authorId":           post.AuthorId,
				"contentType":        post.ContentType,
				"contentIdentity":    post.ContentIdentity,
				"status":             post.Status,
				"visibility":         post.Visibility,
				"circleIds":          asStringSlice(post.CircleIds),
				"assistantUsePolicy": post.AssistantUsePolicy,
				"publishedAt":        post.PublishedAt.Format(time.RFC3339),
			},
			OccurredAt: now.Format(time.RFC3339),
		})
	}
	if s.projector != nil {
		_ = s.projector.Project(ctx, ProjectorEvent{
			Type:          "PostPublished",
			AggregateType: "Post",
			AggregateID:   post.ID,
			Payload: map[string]any{
				"_id":                post.ID,
				"authorId":           post.AuthorId,
				"contentType":        post.ContentType,
				"contentIdentity":    post.ContentIdentity,
				"status":             post.Status,
				"visibility":         post.Visibility,
				"circleIds":          asStringSlice(post.CircleIds),
				"assistantUsePolicy": post.AssistantUsePolicy,
				"publishedAt":        post.PublishedAt.Format(time.RFC3339),
			},
			OccurredAt: now,
		})
	}
	return post, nil
}

func (s *PostService) UpdatePostSettings(ctx context.Context, postID, userID string, payload map[string]any) (*postmodel.Post, error) {
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
			"无权更新内容设置",
			"author mismatch",
			false,
		)
	}
	if err := applyPostSettingsPayload(post, payload); err != nil {
		return nil, err
	}
	now := time.Now().UTC()
	post.UpdatedAt = now
	if !s.store.Update(ctx, post.ID, post) {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "update_failed"),
			"更新内容设置失败",
			"post disappeared while updating settings",
			true,
		)
	}
	s.syncDistributionsFromPost(post)
	s.publishPostEvent(ctx, "PostSettingsUpdated", post, map[string]any{
		"_id":                post.ID,
		"authorId":           post.AuthorId,
		"contentType":        post.ContentType,
		"contentIdentity":    post.ContentIdentity,
		"status":             post.Status,
		"visibility":         post.Visibility,
		"circleIds":          asStringSlice(post.CircleIds),
		"assistantUsePolicy": post.AssistantUsePolicy,
		"publishedAt":        formatTimePtr(post.PublishedAt),
		"title":              post.Title,
		"tags":               asStringSlice(post.Tags),
		"coverUrl":           post.CoverUrl,
	}, now)
	s.projectPostEvent(ctx, "PostSettingsUpdated", post, map[string]any{
		"_id":                post.ID,
		"authorId":           post.AuthorId,
		"contentType":        post.ContentType,
		"contentIdentity":    post.ContentIdentity,
		"status":             post.Status,
		"visibility":         post.Visibility,
		"circleIds":          asStringSlice(post.CircleIds),
		"assistantUsePolicy": post.AssistantUsePolicy,
		"publishedAt":        formatTimePtr(post.PublishedAt),
		"title":              post.Title,
		"tags":               asStringSlice(post.Tags),
		"coverUrl":           post.CoverUrl,
	}, now)
	return post, nil
}

func (s *PostService) PromotePostToWork(ctx context.Context, postID, userID string, payload map[string]any) (*postmodel.Post, error) {
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
			"无权升级该内容",
			"author mismatch",
			false,
		)
	}
	post.ContentIdentity = "work"
	if contentType := strings.TrimSpace(asString(payload["contentType"])); contentType != "" {
		post.ContentType = contentType
	} else {
		post.ContentType = recommendedPromotedContentType(post)
	}
	if title, exists := payload["title"]; exists {
		post.Title = strings.TrimSpace(asString(title))
	}
	if summary, exists := payload["summary"]; exists {
		post.Summary = strings.TrimSpace(asString(summary))
	}
	if tags, exists := payload["tags"]; exists {
		post.Tags = asStringSlice(tags)
	}
	if coverURL, exists := payload["coverUrl"]; exists {
		post.CoverUrl = strings.TrimSpace(asString(coverURL))
	}
	if err := applyPostSettingsPayload(post, payload); err != nil {
		return nil, err
	}
	now := time.Now().UTC()
	post.UpdatedAt = now
	if !s.store.Update(ctx, post.ID, post) {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "update_failed"),
			"升级作品失败",
			"post disappeared while promoting",
			true,
		)
	}
	s.syncDistributionsFromPost(post)
	s.publishPostEvent(ctx, "PostPromotedToWork", post, map[string]any{
		"_id":                post.ID,
		"authorId":           post.AuthorId,
		"contentType":        post.ContentType,
		"contentIdentity":    post.ContentIdentity,
		"status":             post.Status,
		"visibility":         post.Visibility,
		"circleIds":          asStringSlice(post.CircleIds),
		"publishedAt":        formatTimePtr(post.PublishedAt),
		"title":              post.Title,
		"summary":            post.Summary,
		"coverUrl":           post.CoverUrl,
		"tags":               asStringSlice(post.Tags),
		"assistantUsePolicy": post.AssistantUsePolicy,
	}, now)
	s.projectPostEvent(ctx, "PostPromotedToWork", post, map[string]any{
		"_id":                post.ID,
		"authorId":           post.AuthorId,
		"contentType":        post.ContentType,
		"contentIdentity":    post.ContentIdentity,
		"status":             post.Status,
		"visibility":         post.Visibility,
		"circleIds":          asStringSlice(post.CircleIds),
		"publishedAt":        formatTimePtr(post.PublishedAt),
		"title":              post.Title,
		"summary":            post.Summary,
		"coverUrl":           post.CoverUrl,
		"tags":               asStringSlice(post.Tags),
		"assistantUsePolicy": post.AssistantUsePolicy,
	}, now)
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
	if !s.store.Update(ctx, post.ID, post) {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "delete_failed"),
			"删除内容失败",
			"post disappeared while deleting",
			true,
		)
	}
	s.mu.Lock()
	s.tombstones[post.ID] = now
	delete(s.distributions, post.ID)
	delete(s.reshares, post.ID)
	s.mu.Unlock()
	s.publishPostEvent(ctx, "PostDeleted", post, map[string]any{
		"_id":             post.ID,
		"authorId":        post.AuthorId,
		"contentType":     post.ContentType,
		"contentIdentity": post.ContentIdentity,
		"deletedAt":       post.DeletedAt.Format(time.RFC3339),
	}, now)
	s.projectPostEvent(ctx, "PostDeleted", post, map[string]any{
		"_id":             post.ID,
		"contentType":     post.ContentType,
		"contentIdentity": post.ContentIdentity,
		"deletedAt":       post.DeletedAt.Format(time.RFC3339),
	}, now)
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
	if !supportsCircleDistribution(post.Visibility) {
		return nil, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"发布到圈子前需设置为公开或圈内可见",
			"visibility must be public or circle_visible",
		)
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
	now := time.Now().UTC()
	post.UpdatedAt = now
	_ = s.store.Update(ctx, post.ID, post)
	s.syncDistributionsFromPost(post)
	s.publishPostEvent(ctx, "PostSettingsUpdated", post, map[string]any{
		"_id":                post.ID,
		"authorId":           post.AuthorId,
		"contentType":        post.ContentType,
		"contentIdentity":    post.ContentIdentity,
		"status":             post.Status,
		"visibility":         post.Visibility,
		"circleIds":          asStringSlice(post.CircleIds),
		"assistantUsePolicy": post.AssistantUsePolicy,
		"publishedAt":        formatTimePtr(post.PublishedAt),
		"title":              post.Title,
		"tags":               asStringSlice(post.Tags),
		"coverUrl":           post.CoverUrl,
	}, now)
	s.projectPostEvent(ctx, "PostSettingsUpdated", post, map[string]any{
		"_id":                post.ID,
		"authorId":           post.AuthorId,
		"contentType":        post.ContentType,
		"contentIdentity":    post.ContentIdentity,
		"status":             post.Status,
		"visibility":         post.Visibility,
		"circleIds":          asStringSlice(post.CircleIds),
		"assistantUsePolicy": post.AssistantUsePolicy,
		"publishedAt":        formatTimePtr(post.PublishedAt),
		"title":              post.Title,
		"tags":               asStringSlice(post.Tags),
		"coverUrl":           post.CoverUrl,
	}, now)
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
	if !supportsCircleDistribution(post.Visibility) {
		return nil, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"发布到圈子前需设置为公开或圈内可见",
			"visibility must be public or circle_visible",
		)
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
		return normalizePostForRead(post), true, false
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	_, deleted := s.tombstones[strings.TrimSpace(postID)]
	return nil, false, deleted
}

func (s *PostService) GetPostForViewer(
	ctx context.Context,
	postID, viewerID string,
	viewerCircleIDs []string,
) (*postmodel.Post, bool, bool, bool) {
	post, ok, deleted := s.GetPostOrTombstone(ctx, postID)
	if !ok {
		return nil, false, deleted, false
	}
	if !canViewPost(post, viewerID, viewerCircleIDs) {
		return nil, false, false, true
	}
	return post, true, false, false
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

func (s *PostService) AddComment(ctx context.Context, postID, userID, content, replyToCommentID, personaId string) (map[string]any, int64, error) {
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
	contentRunes := []rune(content)
	if len(contentRunes) > s.commentMaxLen {
		return nil, 0, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "comment_too_long"),
			fmt.Sprintf("评论超出字数限制（最多 %d 字）", s.commentMaxLen),
			fmt.Sprintf("comment length %d exceeds max %d", len(contentRunes), s.commentMaxLen),
			false,
		)
	}

	replyToCommentID = strings.TrimSpace(replyToCommentID)
	var replyToUserId string
	if replyToCommentID != "" {
		for _, c := range s.comments[post.ID] {
			if cid, _ := c["_id"].(string); cid == replyToCommentID {
				replyToUserId, _ = c["authorId"].(string)
				rc, _ := c["replyCount"].(int64)
				c["replyCount"] = rc + 1
				break
			}
		}
	}

	now := time.Now().UTC()
	post.CommentCount++
	post.UpdatedAt = now
	_ = s.store.Update(ctx, post.ID, post)

	isAuthor := userID == post.AuthorId
	comment := map[string]any{
		"_id":              fmt.Sprintf("comment_%d", now.UnixNano()),
		"postId":           post.ID,
		"authorId":         userID,
		"personaId":        strings.TrimSpace(personaId),
		"content":          content,
		"replyToCommentId": replyToCommentID,
		"replyToUserId":    replyToUserId,
		"replyCount":       int64(0),
		"likeCount":        int64(0),
		"status":           "visible",
		"isAuthor":         isAuthor,
		"createdAt":        now.Format(time.RFC3339),
		"deletedAt":        "",
	}
	s.comments[post.ID] = append(s.comments[post.ID], comment)

	if s.publisher != nil {
		_ = s.publisher.Publish(ctx, repository.DomainEvent{
			Type:          "CommentCreated",
			AggregateType: "Post",
			AggregateID:   post.ID,
			Payload: map[string]any{
				"commentId":     comment["_id"],
				"postId":        post.ID,
				"authorId":      userID,
				"content":       content,
				"replyToUserId": replyToUserId,
			},
			OccurredAt: now.Format(time.RFC3339),
		})
	}

	return comment, post.CommentCount, nil
}

func (s *PostService) ListComments(_ context.Context, postID, cursor, sort string, limit int) ([]map[string]any, string, error) {
	if limit <= 0 {
		limit = 20
	}
	s.mu.Lock()
	defer s.mu.Unlock()

	all := s.comments[strings.TrimSpace(postID)]
	active := make([]map[string]any, 0, len(all))
	for _, c := range all {
		if del, _ := c["deletedAt"].(string); del != "" {
			continue
		}
		active = append(active, c)
	}

	if sort == "hot" {
		sortCommentsByHot(active)
	} else {
		for i, j := 0, len(active)-1; i < j; i, j = i+1, j-1 {
			active[i], active[j] = active[j], active[i]
		}
	}

	startIdx := 0
	if cursor != "" {
		for i, c := range active {
			if cid, _ := c["_id"].(string); cid == cursor {
				startIdx = i + 1
				break
			}
		}
	}

	if startIdx >= len(active) {
		return []map[string]any{}, "", nil
	}
	end := startIdx + limit
	if end > len(active) {
		end = len(active)
	}
	page := active[startIdx:end]
	nextCursor := ""
	if end < len(active) {
		if cid, ok := page[len(page)-1]["_id"].(string); ok {
			nextCursor = cid
		}
	}
	return page, nextCursor, nil
}

func sortCommentsByHot(comments []map[string]any) {
	for i := 1; i < len(comments); i++ {
		for j := i; j > 0; j-- {
			if hotScore(comments[j]) > hotScore(comments[j-1]) {
				comments[j], comments[j-1] = comments[j-1], comments[j]
			}
		}
	}
}

func hotScore(c map[string]any) float64 {
	likes, _ := c["likeCount"].(int64)
	replies, _ := c["replyCount"].(int64)
	return float64(likes)*10 + float64(replies)*5
}

func (s *PostService) DeleteComment(ctx context.Context, postID, commentID, userID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	comments := s.comments[strings.TrimSpace(postID)]
	found := false
	for i, c := range comments {
		cid, _ := c["_id"].(string)
		if cid != strings.TrimSpace(commentID) {
			continue
		}
		author, _ := c["authorId"].(string)
		if userID != "" && author != "" && author != userID {
			return rterr.NewAppError(
				rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "comment_forbidden_delete"),
				"无权删除此评论",
				"comment author mismatch",
				false,
			)
		}
		comments[i]["deletedAt"] = time.Now().UTC().Format(time.RFC3339)
		comments[i]["status"] = "deleted"
		found = true

		if parentID, _ := c["replyToCommentId"].(string); parentID != "" {
			for _, pc := range comments {
				if pid, _ := pc["_id"].(string); pid == parentID {
					rc, _ := pc["replyCount"].(int64)
					if rc > 0 {
						pc["replyCount"] = rc - 1
					}
					break
				}
			}
		}
		break
	}
	if !found {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"评论不存在",
			"comment not found",
			false,
		)
	}

	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if ok && post.CommentCount > 0 {
		post.CommentCount--
		post.UpdatedAt = time.Now().UTC()
		_ = s.store.Update(ctx, post.ID, post)
	}

	if s.publisher != nil {
		_ = s.publisher.Publish(ctx, repository.DomainEvent{
			Type:          "CommentDeleted",
			AggregateType: "Post",
			AggregateID:   strings.TrimSpace(postID),
			Payload: map[string]any{
				"commentId": commentID,
				"postId":    postID,
			},
			OccurredAt: time.Now().UTC().Format(time.RFC3339),
		})
	}
	return nil
}

func (s *PostService) LikeComment(ctx context.Context, commentID, userID string) (int64, bool, error) {
	userID = strings.TrimSpace(userID)
	if userID == "" {
		userID = "guest"
	}
	commentID = strings.TrimSpace(commentID)

	s.mu.Lock()
	defer s.mu.Unlock()

	byComment, ok := s.commentLikes[commentID]
	if !ok {
		byComment = map[string]bool{}
		s.commentLikes[commentID] = byComment
	}
	if byComment[userID] {
		return 0, false, nil
	}
	byComment[userID] = true

	var likeCount int64
	for _, comments := range s.comments {
		for _, c := range comments {
			if cid, _ := c["_id"].(string); cid == commentID {
				lc, _ := c["likeCount"].(int64)
				lc++
				c["likeCount"] = lc
				likeCount = lc
				break
			}
		}
	}

	if s.publisher != nil {
		_ = s.publisher.Publish(ctx, repository.DomainEvent{
			Type:          "CommentLiked",
			AggregateType: "Post",
			Payload: map[string]any{
				"commentId": commentID,
				"userId":    userID,
				"likeCount": likeCount,
			},
			OccurredAt: time.Now().UTC().Format(time.RFC3339),
		})
	}

	return likeCount, true, nil
}

func (s *PostService) UnlikeComment(_ context.Context, commentID, userID string) (int64, bool, error) {
	userID = strings.TrimSpace(userID)
	if userID == "" {
		userID = "guest"
	}
	commentID = strings.TrimSpace(commentID)

	s.mu.Lock()
	defer s.mu.Unlock()

	byComment := s.commentLikes[commentID]
	if !byComment[userID] {
		return 0, false, nil
	}
	delete(byComment, userID)

	var likeCount int64
	for _, comments := range s.comments {
		for _, c := range comments {
			if cid, _ := c["_id"].(string); cid == commentID {
				lc, _ := c["likeCount"].(int64)
				if lc > 0 {
					lc--
				}
				c["likeCount"] = lc
				likeCount = lc
				break
			}
		}
	}

	return likeCount, true, nil
}

func (s *PostService) IsCommentLiked(commentID, userID string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.commentLikes[strings.TrimSpace(commentID)][strings.TrimSpace(userID)]
}

func (s *PostService) ListCommentsByAuthor(_ context.Context, userID, cursor string, limit int) ([]map[string]any, string, error) {
	if limit <= 0 {
		limit = 20
	}
	userID = strings.TrimSpace(userID)
	s.mu.Lock()
	defer s.mu.Unlock()

	var all []map[string]any
	for _, comments := range s.comments {
		for _, c := range comments {
			if del, _ := c["deletedAt"].(string); del != "" {
				continue
			}
			if aid, _ := c["authorId"].(string); aid == userID {
				all = append(all, c)
			}
		}
	}

	for i, j := 0, len(all)-1; i < j; i, j = i+1, j-1 {
		all[i], all[j] = all[j], all[i]
	}

	startIdx := 0
	if cursor != "" {
		for i, c := range all {
			if cid, _ := c["_id"].(string); cid == cursor {
				startIdx = i + 1
				break
			}
		}
	}
	if startIdx >= len(all) {
		return []map[string]any{}, "", nil
	}
	end := startIdx + limit
	if end > len(all) {
		end = len(all)
	}
	page := all[startIdx:end]
	nextCursor := ""
	if end < len(all) {
		if cid, ok := page[len(page)-1]["_id"].(string); ok {
			nextCursor = cid
		}
	}
	return page, nextCursor, nil
}

func (s *PostService) ListCommentsForPostAuthor(ctx context.Context, userID, cursor string, limit int) ([]map[string]any, string, error) {
	if limit <= 0 {
		limit = 20
	}
	userID = strings.TrimSpace(userID)
	s.mu.Lock()
	defer s.mu.Unlock()

	authorPostIDs := map[string]bool{}
	for _, p := range s.store.ListByAuthor(ctx, userID, 10000, "") {
		authorPostIDs[p.ID] = true
	}

	var all []map[string]any
	for postID, comments := range s.comments {
		if !authorPostIDs[postID] {
			continue
		}
		for _, c := range comments {
			if del, _ := c["deletedAt"].(string); del != "" {
				continue
			}
			if aid, _ := c["authorId"].(string); aid != userID {
				all = append(all, c)
			}
		}
	}

	for i, j := 0, len(all)-1; i < j; i, j = i+1, j-1 {
		all[i], all[j] = all[j], all[i]
	}

	startIdx := 0
	if cursor != "" {
		for i, c := range all {
			if cid, _ := c["_id"].(string); cid == cursor {
				startIdx = i + 1
				break
			}
		}
	}
	if startIdx >= len(all) {
		return []map[string]any{}, "", nil
	}
	end := startIdx + limit
	if end > len(all) {
		end = len(all)
	}
	page := all[startIdx:end]
	nextCursor := ""
	if end < len(all) {
		if cid, ok := page[len(page)-1]["_id"].(string); ok {
			nextCursor = cid
		}
	}
	return page, nextCursor, nil
}

func (s *PostService) GetAppConfig() map[string]any {
	runtimeConfig := normalizeStoryRuntimeConfig(s.storyRuntime)
	canaryMatrix := make([]map[string]any, 0, len(runtimeConfig.CanaryMatrix))
	for _, stage := range runtimeConfig.CanaryMatrix {
		canaryMatrix = append(canaryMatrix, map[string]any{
			"stage":          stage.Stage,
			"rolloutPercent": stage.RolloutPercent,
		})
	}
	featureFlags := make(map[string]any, len(runtimeConfig.FeatureFlags))
	for key, value := range runtimeConfig.FeatureFlags {
		featureFlags[key] = value
	}
	return map[string]any{
		"content": map[string]any{
			"comment": map[string]any{
				"max_length":          s.commentMaxLen,
				"reply_preview_count": 3,
				"fold_line_count":     3,
			},
			"feature_flags": featureFlags,
			"gray_release": map[string]any{
				"experiment_bucket": runtimeConfig.ExperimentBucket,
				"current_stage":     runtimeConfig.CurrentStage,
				"canary_matrix":     canaryMatrix,
			},
		},
	}
}

func (s *PostService) GetCounters(ctx context.Context, postID string) (map[string]any, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
			false,
		)
	}
	return map[string]any{
		"like":     post.LikeCount,
		"comment":  post.CommentCount,
		"favorite": post.FavoriteCount,
		"share":    post.ShareCount,
	}, nil
}

func (s *PostService) ListUserPosts(
	ctx context.Context,
	authorID, viewerID string,
	viewerCircleIDs []string,
	identity, requestedType, cursor string,
	limit int,
) ([]postmodel.Post, string, error) {
	if limit <= 0 {
		limit = 20
	}
	posts := s.store.ListByAuthor(ctx, strings.TrimSpace(authorID), limit*5, cursor)
	filtered := make([]postmodel.Post, 0, len(posts))
	expectedIdentity := normalizeRequestedIdentity(identity)
	expectedType := normalizeRequestType(requestedType)
	for _, stored := range posts {
		post := *normalizePostForRead(&stored)
		if !canViewPost(&post, viewerID, viewerCircleIDs) {
			continue
		}
		postIdentity := strings.TrimSpace(strings.ToLower(post.ContentIdentity))
		if expectedIdentity != "" && postIdentity != expectedIdentity {
			continue
		}
		if expectedType != "" {
			viewType := mapContentTypeToViewType(post.ContentType)
			if expectedIdentity != "moment" && viewType != expectedType {
				continue
			}
		}
		filtered = append(filtered, post)
	}
	nextCursor := ""
	if len(filtered) > limit {
		nextCursor = filtered[limit-1].ID
		filtered = filtered[:limit]
	}
	return filtered, nextCursor, nil
}

func (s *PostService) GetHelperRead(ctx context.Context, postID string) (map[string]any, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
			false,
		)
	}
	if strings.TrimSpace(post.ContentType) != "article" {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"仅支持文章类型的辅助阅读",
			"helper-read only for articles",
			false,
		)
	}
	summary := post.Summary
	if summary == "" {
		body := strings.TrimSpace(post.Body)
		if len(body) > 200 {
			body = body[:200]
		}
		summary = body
	}
	return map[string]any{
		"postId":      post.ID,
		"contentType": post.ContentType,
		"title":       post.Title,
		"summary":     summary,
	}, nil
}

func (s *PostService) RebuildProjectionDryRun(
	ctx context.Context,
	apply bool,
) (ProjectionRebuildReport, error) {
	report := ProjectionRebuildReport{DryRun: !apply}
	posts := s.store.ListAll(ctx)
	now := time.Now().UTC()
	for _, stored := range posts {
		rawIdentity := strings.TrimSpace(strings.ToLower(stored.ContentIdentity))
		rawAssistantUsePolicy := strings.TrimSpace(strings.ToLower(stored.AssistantUsePolicy))
		post := normalizePostForRead(&stored)
		if post == nil {
			continue
		}
		report.TotalPosts++
		switch strings.TrimSpace(strings.ToLower(post.Status)) {
		case "deleted":
			report.DeletedPosts++
		case "published":
			report.PublishedPosts++
		default:
			report.DraftPosts++
		}
		switch normalizeVisibility(post.Visibility) {
		case "private":
			report.PrivatePosts++
		case "circle_visible":
			report.CircleVisiblePosts++
		default:
			report.PublicPosts++
		}
		if rawIdentity == "" {
			report.BackfilledContentIdentity++
		}
		if rawAssistantUsePolicy == "" {
			report.BackfilledAssistantUsePolicy++
		}
		if strings.EqualFold(post.AssistantUsePolicy, "exclude") {
			report.AssistantExcludedPosts++
		}
		if strings.EqualFold(post.Status, "published") && normalizeVisibility(post.Visibility) == "public" {
			report.DiscoveryEligiblePosts++
		} else {
			report.DiscoveryRevokedPosts++
		}
		if !apply {
			continue
		}
		eventType := projectionEventTypeForPost(post)
		s.projectPostEvent(ctx, eventType, post, projectionPayloadForPost(post), now)
	}
	return report, nil
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

func formatTimePtr(t time.Time) string {
	if t.IsZero() {
		return ""
	}
	return t.UTC().Format(time.RFC3339)
}

func projectionEventTypeForPost(post *postmodel.Post) string {
	if post == nil {
		return ""
	}
	switch strings.TrimSpace(strings.ToLower(post.Status)) {
	case "deleted":
		return "PostDeleted"
	case "published":
		return "PostPublished"
	default:
		return "PostCreated"
	}
}

func projectionPayloadForPost(post *postmodel.Post) map[string]any {
	if post == nil {
		return nil
	}
	return map[string]any{
		"_id":                post.ID,
		"authorId":           post.AuthorId,
		"contentType":        post.ContentType,
		"contentIdentity":    post.ContentIdentity,
		"status":             post.Status,
		"visibility":         normalizeVisibility(post.Visibility),
		"circleIds":          asStringSlice(post.CircleIds),
		"assistantUsePolicy": post.AssistantUsePolicy,
		"publishedAt":        formatTimePtr(post.PublishedAt),
		"title":              post.Title,
		"summary":            post.Summary,
		"coverUrl":           post.CoverUrl,
		"tags":               asStringSlice(post.Tags),
	}
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

func normalizeContentIdentity(contentType, requested string) string {
	requested = strings.TrimSpace(strings.ToLower(requested))
	if requested != "" {
		return requested
	}
	switch strings.TrimSpace(strings.ToLower(contentType)) {
	case "micro":
		return "moment"
	default:
		return "work"
	}
}

func normalizeAssistantUsePolicy(value string) string {
	switch strings.TrimSpace(strings.ToLower(value)) {
	case "", "inherit":
		return "inherit"
	case "exclude":
		return "exclude"
	default:
		return "inherit"
	}
}

func normalizeVisibility(value string) string {
	switch strings.TrimSpace(strings.ToLower(value)) {
	case "", "public":
		return "public"
	case "private":
		return "private"
	case "circle_visible", "circle-visible", "circle":
		return "circle_visible"
	default:
		return "public"
	}
}

func supportsCircleDistribution(visibility string) bool {
	switch normalizeVisibility(visibility) {
	case "public", "circle_visible":
		return true
	default:
		return false
	}
}

func sharesCircle(postCircleIDs, viewerCircleIDs []string) bool {
	if len(postCircleIDs) == 0 || len(viewerCircleIDs) == 0 {
		return false
	}
	allowed := make(map[string]struct{}, len(postCircleIDs))
	for _, circleID := range postCircleIDs {
		circleID = strings.TrimSpace(circleID)
		if circleID == "" {
			continue
		}
		allowed[circleID] = struct{}{}
	}
	for _, circleID := range viewerCircleIDs {
		circleID = strings.TrimSpace(circleID)
		if circleID == "" {
			continue
		}
		if _, ok := allowed[circleID]; ok {
			return true
		}
	}
	return false
}

func validateContentIdentity(contentType, identity string) error {
	contentType = strings.TrimSpace(strings.ToLower(contentType))
	identity = strings.TrimSpace(strings.ToLower(identity))
	switch identity {
	case "moment":
		if contentType != "micro" {
			return rterr.NewInvalidArgument(
				rterr.ModuleContent,
				"点滴内容类型不合法",
				"moment must use contentType=micro",
			)
		}
	case "work":
		if contentType == "micro" {
			return rterr.NewInvalidArgument(
				rterr.ModuleContent,
				"作品内容类型不合法",
				"work cannot use contentType=micro",
			)
		}
	default:
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"内容身份不合法",
			"unsupported contentIdentity",
		)
	}
	return nil
}

func applyPostSettingsPayload(post *postmodel.Post, payload map[string]any) error {
	if contentIdentity, exists := payload["contentIdentity"]; exists {
		post.ContentIdentity = normalizeContentIdentity(
			post.ContentType,
			strings.TrimSpace(asString(contentIdentity)),
		)
	}
	if visibility, exists := payload["visibility"]; exists {
		post.Visibility = normalizeVisibility(asString(visibility))
	}
	if circles, exists := payload["circleIds"]; exists {
		post.CircleIds = asStringSlice(circles)
	}
	if assistantUsePolicy, exists := payload["assistantUsePolicy"]; exists {
		post.AssistantUsePolicy = normalizeAssistantUsePolicy(
			strings.TrimSpace(asString(assistantUsePolicy)),
		)
	}
	if post.ContentIdentity == "" {
		post.ContentIdentity = normalizeContentIdentity(post.ContentType, "")
	}
	if post.AssistantUsePolicy == "" {
		post.AssistantUsePolicy = "inherit"
	}
	if err := validateContentIdentity(post.ContentType, post.ContentIdentity); err != nil {
		return err
	}
	post.Visibility = normalizeVisibility(post.Visibility)
	if circles := asStringSlice(post.CircleIds); len(circles) > 0 && !supportsCircleDistribution(post.Visibility) {
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"发布到圈子前需设置为公开或圈内可见",
			"visibility must be public or circle_visible",
		)
	}
	return nil
}

func recommendedPromotedContentType(post *postmodel.Post) string {
	if strings.TrimSpace(post.VideoUrl) != "" {
		return "video"
	}
	if len(asStringSlice(post.MediaUrls)) > 0 {
		return "image"
	}
	return "article"
}

func validateCreatePostPayload(post *postmodel.Post) error {
	if post.ContentIdentity == "" {
		post.ContentIdentity = normalizeContentIdentity(post.ContentType, "")
	}
	if post.AssistantUsePolicy == "" {
		post.AssistantUsePolicy = "inherit"
	}
	if err := validateContentIdentity(post.ContentType, post.ContentIdentity); err != nil {
		return err
	}
	post.Visibility = normalizeVisibility(post.Visibility)
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
	if circles := asStringSlice(post.CircleIds); len(circles) > 0 && !supportsCircleDistribution(post.Visibility) {
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"发布到圈子前需设置为公开或圈内可见",
			"visibility must be public or circle_visible",
		)
	}
	return nil
}
