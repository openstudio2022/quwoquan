package application

import (
	"context"
	"fmt"
	"log/slog"
	"sort"
	"strconv"
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

type articleDocumentSnapshot struct {
	Title      string
	Body       string
	MediaURLs  []string
	CoverURL   string
	Template   string
	FontPreset string
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

func directShareKey(userID string) string {
	return "direct:" + strings.TrimSpace(userID)
}

func hasActiveShareForUser(shares map[string]bool, userID string) bool {
	normalizedUserID := strings.TrimSpace(userID)
	if normalizedUserID == "" {
		return false
	}
	for shareKey, active := range shares {
		if !active {
			continue
		}
		if shareActorID(shareKey) == normalizedUserID {
			return true
		}
	}
	return false
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
		ID:               fmt.Sprintf("post_%d", now.UnixNano()),
		AuthorId:         strings.TrimSpace(asString(payload["authorId"])),
		PersonaContextVersion: asInt64Flexible(
			payload["personaContextVersion"],
		),
		AuthorDisplayNameSnapshot: strings.TrimSpace(
			asString(payload["authorDisplayNameSnapshot"]),
		),
		AuthorAvatarUrlSnapshot: strings.TrimSpace(
			asString(payload["authorAvatarUrlSnapshot"]),
		),
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
		ArticleDocument:     asMap(payload["articleDocument"]),
		ArticleTemplate:     strings.TrimSpace(asString(payload["articleTemplate"])),
		ArticleFontPreset:   strings.TrimSpace(asString(payload["articleFontPreset"])),
		Status:              "draft",
		ModerationStatus:    "pending",
		CreatedAt:           now,
		UpdatedAt:           now,
	}
	if post.AuthorId == "" {
		return nil, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"authorId 不能为空",
			"missing authorId/subAccountId",
		)
	}
	if post.SourceType == "" {
		post.SourceType = "original"
	}
	s.syncArticleDocumentSnapshot(post)
	if err := validateCreatePostPayload(post); err != nil {
		return nil, err
	}
	if err := s.store.Create(ctx, post); err != nil {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "create_failed"),
			"创建内容失败",
			err.Error(),
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
		)
	}
	if strings.EqualFold(strings.TrimSpace(post.Status), "published") {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "conflict"),
			"内容发布后不可修改",
			"post immutable after publish",
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
	if articleDocument, exists := payload["articleDocument"]; exists {
		post.ArticleDocument = asMap(articleDocument)
	}
	post.UpdatedAt = time.Now().UTC()
	s.syncArticleDocumentSnapshot(post)
	if err := validateCreatePostPayload(post); err != nil {
		return nil, err
	}
	if updated := s.store.Update(ctx, post.ID, post); !updated {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "update_failed"),
			"更新内容失败",
			"post disappeared while updating",
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
		)
	}
	if strings.EqualFold(post.Status, "deleted") {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "conflict"),
			"内容已删除",
			"post deleted",
		)
	}
	if err := applyPostSettingsPayload(post, payload); err != nil {
		return nil, err
	}
	s.syncArticleDocumentSnapshot(post)
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

func promoteSettingsPayload(payload map[string]any) map[string]any {
	settings := map[string]any{}
	for _, key := range []string{
		"primaryHomepageId",
		"primaryHomepageType",
		"primaryHomepageSnapshot",
		"visibility",
		"circleIds",
		"groupId",
		"nodeId",
		"assistantUsePolicy",
	} {
		if value, exists := payload[key]; exists {
			settings[key] = value
		}
	}
	return settings
}

func (s *PostService) UpdatePostSettings(ctx context.Context, postID, userID string, payload map[string]any) (*postmodel.Post, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	if post.AuthorId != "" && userID != "" && post.AuthorId != userID {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "forbidden"),
			"无权更新内容设置",
			"author mismatch",
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
		)
	}
	if post.AuthorId != "" && userID != "" && post.AuthorId != userID {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "forbidden"),
			"无权升级该内容",
			"author mismatch",
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
	if articleDocument, exists := payload["articleDocument"]; exists {
		post.ArticleDocument = asMap(articleDocument)
	}
	if err := applyPostSettingsPayload(post, promoteSettingsPayload(payload)); err != nil {
		return nil, err
	}
	s.syncArticleDocumentSnapshot(post)
	now := time.Now().UTC()
	post.UpdatedAt = now
	if !s.store.Update(ctx, post.ID, post) {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "update_failed"),
			"升级作品失败",
			"post disappeared while promoting",
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
		)
	}
	if userID != "" && post.AuthorId != "" && post.AuthorId != userID {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "forbidden"),
			"无权删除此内容",
			"author mismatch",
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
		)
	}
	if post.AuthorId != "" && userID != "" && post.AuthorId != userID {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "forbidden"),
			"无权修改圈子分发关系",
			"author mismatch",
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

func (s *PostService) applyShareRecordLocked(
	ctx context.Context,
	post *postmodel.Post,
	shareKey string,
	userID string,
	active bool,
) (int64, bool, bool) {
	if post == nil {
		return 0, false, false
	}
	shares, ok := s.reshares[post.ID]
	if !ok {
		shares = map[string]bool{}
		s.reshares[post.ID] = shares
	}
	wasActive := shares[shareKey]
	changed := wasActive != active
	if changed {
		if active {
			shares[shareKey] = true
			post.ShareCount++
		} else {
			delete(shares, shareKey)
			if post.ShareCount > 0 {
				post.ShareCount--
			}
		}
		post.UpdatedAt = time.Now().UTC()
		_ = s.store.Update(ctx, post.ID, post)
	}
	return post.ShareCount, changed, hasActiveShareForUser(shares, userID)
}

func (s *PostService) SharePost(ctx context.Context, postID, userID string) (int64, bool, bool, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return 0, false, false, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	if strings.EqualFold(post.Status, "deleted") {
		return 0, false, false, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "conflict"),
			"内容已删除",
			"post deleted",
		)
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		userID = AnonymousFallbackSubAccountID
	}

	s.mu.Lock()
	shareCount, changed, shared := s.applyShareRecordLocked(
		ctx,
		post,
		directShareKey(userID),
		userID,
		true,
	)
	s.mu.Unlock()
	return shareCount, changed, shared, nil
}

func (s *PostService) UnsharePost(ctx context.Context, postID, userID string) (int64, bool, bool, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return 0, false, false, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		userID = AnonymousFallbackSubAccountID
	}

	s.mu.Lock()
	shareCount, changed, shared := s.applyShareRecordLocked(
		ctx,
		post,
		directShareKey(userID),
		userID,
		false,
	)
	s.mu.Unlock()
	return shareCount, changed, shared, nil
}

func (s *PostService) RepostToCircle(ctx context.Context, postID, userID, circleID, quote string) (map[string]any, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	if strings.EqualFold(post.Status, "deleted") {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "conflict"),
			"内容已删除",
			"post deleted",
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
		userID = AnonymousFallbackSubAccountID
	}
	key := circleID + ":" + userID
	s.mu.Lock()
	shareCount, changed, _ := s.applyShareRecordLocked(
		ctx,
		post,
		key,
		userID,
		true,
	)
	s.mu.Unlock()
	return map[string]any{
		"postId":         post.ID,
		"sourcePostId":   post.ID,
		"resharerUserId": userID,
		"circleId":       circleID,
		"quoteText":      strings.TrimSpace(quote),
		"type":           "moment",
		"shareCount":     shareCount,
		"changed":        changed,
	}, nil
}

func (s *PostService) InitMediaUpload(_ context.Context, userID, mediaType string) map[string]any {
	now := time.Now().UTC()
	if userID == "" {
		userID = AnonymousFallbackSubAccountID
	}
	mediaID := fmt.Sprintf("media_%d", now.UnixNano())
	sessionID := fmt.Sprintf("upload_%d", now.UnixNano())
	asset := postmodel.MediaAsset{
		ID:               mediaID,
		Type:             defaultString(strings.TrimSpace(mediaType), "image"),
		OriginUrl:        "https://origin.example/media/" + mediaID + "/original.jpg",
		MimeType:         "image/jpeg",
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
		)
	}
	asset, ok := s.mediaAssets[mediaID]
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"媒体不存在",
			"media not found",
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
		asset.DominantColor = "#1A1A1A"
		asset.Lqip = map[string]any{"kind": "color", "value": asset.DominantColor, "w": 16, "h": 16}
		asset.ContentProfile = map[string]any{"hasAlpha": false, "contentClass": "photo", "edgeDensityScore": 0.24, "flatColorScore": 0.18, "textLikeScore": 0.03}
		asset.DerivativePolicyVersion = fmt.Sprintf("%d", time.Now().UTC().Unix())
		asset.Derivatives = map[string]any{"job": map[string]any{"jobId": "img_derivative_" + mediaID, "status": "ready", "retryable": true}, "variants": []map[string]any{{"displayUse": "feedCard", "qualityTier": "standard", "format": "webp", "url": asset.CdnUrl + "?use=feedCard&tier=standard&fmt=webp"}}}
		asset.AccessPolicy = map[string]any{"originalAllowed": true, "allowOriginalView": true, "allowOriginalSave": true, "originalTtlSeconds": 300, "originalSizeBytes": asset.FileSizeBytes, "originalSha256": "dev-sha256-" + mediaID}
		asset.OriginalAccess = map[string]any{"available": true, "requiresExplicitAction": true, "sizeBytes": asset.FileSizeBytes, "format": asset.MimeType, "ttlSeconds": 300}
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
		)
	}
	asset.CoverStrategy = "manual"
	asset.ManualCoverAssetId = strings.TrimSpace(coverAssetID)
	asset.UpdatedAt = time.Now().UTC()
	s.mediaAssets[asset.ID] = asset
	cp := asset
	return &cp, nil
}

func generateArticleSummary(title, body string) string {
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

func (s *PostService) GenerateArticleSummary(title, body string) string {
	return generateArticleSummary(title, body)
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
		)
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		userID = AnonymousFallbackSubAccountID
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
		)
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		userID = AnonymousFallbackSubAccountID
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
		)
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		userID = AnonymousFallbackSubAccountID
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
		)
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		userID = AnonymousFallbackSubAccountID
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

func (s *PostService) GetReactionState(postID, userID string) (liked, favorited, shared bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	normalizedPostID := strings.TrimSpace(postID)
	normalizedUserID := strings.TrimSpace(userID)
	shared = hasActiveShareForUser(s.reshares[normalizedPostID], normalizedUserID)
	byPost, ok := s.reactions[normalizedPostID]
	if !ok {
		return false, false, shared
	}
	state, ok := byPost[normalizedUserID]
	if !ok {
		return false, false, shared
	}
	return state.Liked, state.Favorited, shared
}

func (s *PostService) ListProfileInteractionActivities(
	ctx context.Context,
	profileSubjectID string,
	direction string,
	limit int,
) ([]postmodel.ProfileInteractionActivityView, error) {
	profileSubjectID = strings.TrimSpace(profileSubjectID)
	direction = strings.TrimSpace(direction)
	if profileSubjectID == "" {
		return []postmodel.ProfileInteractionActivityView{}, nil
	}
	if direction == "" {
		direction = "received"
	}
	if limit <= 0 {
		limit = 20
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	items := make([]postmodel.ProfileInteractionActivityView, 0)
	for postID, byUser := range s.reactions {
		post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
		if !ok {
			continue
		}
		for actorID, state := range byUser {
			if !state.Liked {
				continue
			}
			if direction == "received" {
				if post.AuthorId != profileSubjectID || actorID == profileSubjectID {
					continue
				}
			} else if actorID != profileSubjectID {
				continue
			}
			items = append(items, buildProfileInteractionActivityView(
				fmt.Sprintf("like:%s:%s", postID, actorID),
				"like",
				direction,
				actorID,
				post.AuthorId,
				post,
				post.UpdatedAt,
			))
		}
	}

	for postID, comments := range s.comments {
		post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
		if !ok {
			continue
		}
		for _, comment := range comments {
			if deletedAt, _ := comment["deletedAt"].(string); deletedAt != "" {
				continue
			}
			actorID, _ := comment["authorId"].(string)
			if direction == "received" {
				if post.AuthorId != profileSubjectID || actorID == profileSubjectID {
					continue
				}
			} else if actorID != profileSubjectID {
				continue
			}
			items = append(items, buildProfileInteractionActivityView(
				fmt.Sprintf("comment:%s", stringValue(comment["_id"])),
				"comment",
				direction,
				actorID,
				post.AuthorId,
				post,
				parseActivityTime(comment["createdAt"]),
			))
		}
	}

	for postID, shares := range s.reshares {
		post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
		if !ok {
			continue
		}
		for shareKey, active := range shares {
			if !active {
				continue
			}
			actorID := shareActorID(shareKey)
			if actorID == "" {
				continue
			}
			if direction == "received" {
				if post.AuthorId != profileSubjectID || actorID == profileSubjectID {
					continue
				}
			} else if actorID != profileSubjectID {
				continue
			}
			items = append(items, buildProfileInteractionActivityView(
				fmt.Sprintf("share:%s:%s", postID, actorID),
				"share",
				direction,
				actorID,
				post.AuthorId,
				post,
				post.UpdatedAt,
			))
		}
	}

	sort.Slice(items, func(i, j int) bool {
		return items[i].CreatedAt.After(items[j].CreatedAt)
	})
	if len(items) > limit {
		items = items[:limit]
	}
	return items, nil
}

func buildProfileInteractionActivityView(
	activityID string,
	activityType string,
	direction string,
	actorID string,
	targetSubAccountID string,
	post *postmodel.Post,
	createdAt time.Time,
) postmodel.ProfileInteractionActivityView {
	summary := ""
	contentType := ""
	targetContentID := ""
	if post != nil {
		summary = summarizeInteractionTarget(post)
		contentType = post.ContentType
		targetContentID = post.ID
	}
	if createdAt.IsZero() {
		createdAt = time.Now().UTC()
	}
	return postmodel.ProfileInteractionActivityView{
		ActivityId:           activityID,
		ActivityType:         activityType,
		Direction:            direction,
		ActorSubAccountId:    actorID,
		ActorDisplayName:     actorID,
		ActorAvatarUrl:       "",
		TargetSubAccountId:   targetSubAccountID,
		TargetContentId:      targetContentID,
		TargetContentType:    contentType,
		TargetContentSummary: summary,
		CreatedAt:            createdAt,
	}
}

func summarizeInteractionTarget(post *postmodel.Post) string {
	if post == nil {
		return ""
	}
	if summary := strings.TrimSpace(post.Summary); summary != "" {
		return summary
	}
	if title := strings.TrimSpace(post.Title); title != "" {
		return title
	}
	body := strings.TrimSpace(post.Body)
	if len(body) > 60 {
		return body[:60]
	}
	return body
}

func parseActivityTime(raw any) time.Time {
	if s, ok := raw.(string); ok {
		if parsed, err := time.Parse(time.RFC3339, s); err == nil {
			return parsed
		}
	}
	return time.Now().UTC()
}

func deriveArticleDocumentSnapshot(document map[string]any) articleDocumentSnapshot {
	snapshot := articleDocumentSnapshot{
		Template: strings.TrimSpace(asString(document["template"])),
		FontPreset: strings.TrimSpace(
			asString(document["fontPreset"]),
		),
		CoverURL: strings.TrimSpace(asString(document["coverImageUrl"])),
	}
	if snapshot.Template == "" {
		snapshot.Template = strings.TrimSpace(asString(document["articleTemplate"]))
	}
	if snapshot.FontPreset == "" {
		snapshot.FontPreset = strings.TrimSpace(asString(document["articleFontPreset"]))
	}
	if snapshot.CoverURL == "" {
		snapshot.CoverURL = strings.TrimSpace(asString(document["coverUrl"]))
	}
	if len(document) == 0 {
		return snapshot
	}
	appendLine := func(lines []string, line string) []string {
		normalized := strings.TrimSpace(line)
		if normalized == "" {
			return lines
		}
		return append(lines, normalized)
	}
	var lines []string
	orderedIndex := 0
	rawNodes, _ := document["nodes"].([]any)
	for _, rawNode := range rawNodes {
		node := asMap(rawNode)
		if len(node) == 0 {
			continue
		}
		nodeType := strings.TrimSpace(asString(node["type"]))
		text := strings.TrimSpace(asString(node["text"]))
		switch nodeType {
		case "documentTitle", "title":
			if snapshot.Title == "" {
				snapshot.Title = text
			}
			orderedIndex = 0
		case "headingMajor", "headingMinor", "heading2", "heading3", "sectionTitle":
			orderedIndex = 0
			lines = appendLine(lines, text)
		case "orderedItem":
			if text == "" {
				continue
			}
			orderedIndex++
			lines = appendLine(lines, fmt.Sprintf("%d. %s", orderedIndex, text))
		case "bulletItem":
			orderedIndex = 0
			lines = appendLine(lines, "• "+text)
		case "figure", "image":
			orderedIndex = 0
			imageURL := strings.TrimSpace(asString(node["imageUrl"]))
			if imageURL == "" {
				continue
			}
			snapshot.MediaURLs = append(snapshot.MediaURLs, imageURL)
			if snapshot.CoverURL == "" {
				snapshot.CoverURL = imageURL
			}
		default:
			orderedIndex = 0
			lines = appendLine(lines, text)
		}
	}
	if len(rawNodes) == 0 {
		snapshot.Title = strings.TrimSpace(asString(document["title"]))
		snapshot.Body = strings.TrimSpace(asString(document["body"]))
		rawAssets, _ := document["assets"].([]any)
		for _, rawAsset := range rawAssets {
			asset := asMap(rawAsset)
			if len(asset) == 0 {
				continue
			}
			imageURL := strings.TrimSpace(asString(asset["imageUrl"]))
			if imageURL == "" {
				continue
			}
			snapshot.MediaURLs = append(snapshot.MediaURLs, imageURL)
			if snapshot.CoverURL == "" {
				snapshot.CoverURL = imageURL
			}
		}
		if snapshot.CoverURL == "" && len(snapshot.MediaURLs) > 0 {
			snapshot.CoverURL = snapshot.MediaURLs[0]
		}
		return snapshot
	}
	snapshot.Body = strings.Join(lines, "\n")
	if snapshot.CoverURL == "" && len(snapshot.MediaURLs) > 0 {
		snapshot.CoverURL = snapshot.MediaURLs[0]
	}
	return snapshot
}

func (s *PostService) syncArticleDocumentSnapshot(post *postmodel.Post) {
	if post == nil || strings.TrimSpace(post.ContentType) != "article" {
		return
	}
	snapshot := deriveArticleDocumentSnapshot(post.ArticleDocument)
	post.Title = snapshot.Title
	post.Body = snapshot.Body
	post.MediaUrls = snapshot.MediaURLs
	post.CoverUrl = snapshot.CoverURL
	post.ArticleTemplate = snapshot.Template
	post.ArticleFontPreset = snapshot.FontPreset
	post.Summary = generateArticleSummary(snapshot.Title, snapshot.Body)
}

func shareActorID(shareKey string) string {
	parts := strings.Split(strings.TrimSpace(shareKey), ":")
	if len(parts) == 0 {
		return ""
	}
	return strings.TrimSpace(parts[len(parts)-1])
}

func stringValue(raw any) string {
	if value, ok := raw.(string); ok {
		return value
	}
	return ""
}

func (s *PostService) AddComment(
	ctx context.Context,
	postID string,
	userID string,
	content string,
	replyToCommentID string,
	authorID string,
	personaContextVersion string,
) (map[string]any, int64, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return nil, 0, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	userID = strings.TrimSpace(userID)
	authorID = strings.TrimSpace(authorID)
	if authorID == "" {
		authorID = userID
	}
	if authorID == "" {
		return nil, 0, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"authorId 不能为空",
			"missing comment authorId/subAccountId",
		)
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

	isAuthor := authorID == post.AuthorId
	comment := map[string]any{
		"_id":              fmt.Sprintf("comment_%d", now.UnixNano()),
		"postId":           post.ID,
		"authorId":         authorID,
		"personaContextVersion": asInt64Flexible(
			personaContextVersion,
		),
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
				"authorId":      authorID,
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
		userID = AnonymousFallbackSubAccountID
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
		userID = AnonymousFallbackSubAccountID
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

type SearchPostsRequest struct {
	Query         string
	Identity      string
	RequestedType string
	CategoryID    string
	SubCategory   string
	Cursor        string
	Limit         int
}

func (s *PostService) SearchPosts(
	ctx context.Context,
	req SearchPostsRequest,
) ([]postmodel.PostSearchItemView, string, error) {
	limit := req.Limit
	if limit <= 0 {
		limit = 20
	}
	query := strings.TrimSpace(strings.ToLower(req.Query))
	expectedIdentity := normalizeRequestedIdentity(req.Identity)
	expectedType := normalizeRequestType(req.RequestedType)
	posts := s.store.ListPublished(ctx, limit*8, req.Cursor)
	results := make([]postmodel.PostSearchItemView, 0, limit)
	for _, stored := range posts {
		post := *normalizePostForRead(&stored)
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
		matchedField := ""
		highlight := ""
		if query != "" {
			candidates := []struct {
				field string
				value string
			}{
				{field: "title", value: post.Title},
				{field: "summary", value: post.Summary},
				{field: "body", value: post.Body},
				{field: "authorDisplayName", value: post.AuthorDisplayNameSnapshot},
				{field: "locationName", value: post.LocationName},
			}
			for _, candidate := range candidates {
				if strings.Contains(strings.ToLower(strings.TrimSpace(candidate.value)), query) {
					matchedField = candidate.field
					highlight = strings.TrimSpace(candidate.value)
					break
				}
			}
			if matchedField == "" {
				continue
			}
		}
		primaryCircleID := strings.TrimSpace(post.CircleId)
		if primaryCircleID == "" {
			circleIDs := asStringSlice(post.CircleIds)
			if len(circleIDs) > 0 {
				primaryCircleID = strings.TrimSpace(circleIDs[0])
			}
		}
		summary := strings.TrimSpace(post.Summary)
		if summary == "" {
			summary = strings.TrimSpace(post.Body)
		}
		coverURL := strings.TrimSpace(post.CoverUrl)
		if coverURL == "" {
			coverURL = strings.TrimSpace(post.VideoUrl)
		}
		results = append(results, postmodel.PostSearchItemView{
			PostId:            post.ID,
			ContentType:       post.ContentType,
			ContentIdentity:   post.ContentIdentity,
			Title:             post.Title,
			Summary:           summary,
			CoverUrl:          coverURL,
			AuthorId:          post.AuthorId,
			AuthorDisplayName: post.AuthorDisplayNameSnapshot,
			AuthorAvatarUrl:   post.AuthorAvatarUrlSnapshot,
			CircleId:          primaryCircleID,
			CircleName:        "",
			CategoryId:        strings.TrimSpace(req.CategoryID),
			SubCategory:       strings.TrimSpace(req.SubCategory),
			LikeCount:         post.LikeCount,
			HighlightText:     highlight,
			MatchedField:      matchedField,
			PublishedAt:       post.PublishedAt,
		})
		if len(results) >= limit {
			break
		}
	}
	nextCursor := ""
	if len(results) == limit {
		nextCursor = results[len(results)-1].PostId
	}
	return results, nextCursor, nil
}

func (s *PostService) GetHelperRead(ctx context.Context, postID string) (map[string]any, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	if strings.TrimSpace(post.ContentType) != "article" {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"仅支持文章类型的辅助阅读",
			"helper-read only for articles",
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

func asInt64Flexible(v any) int64 {
	switch vv := v.(type) {
	case int64:
		return vv
	case int:
		return int64(vv)
	case float64:
		return int64(vv)
	case string:
		n, err := strconv.ParseInt(strings.TrimSpace(vv), 10, 64)
		if err == nil {
			return n
		}
	}
	return 0
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
	for _, key := range []string{
		"title",
		"body",
		"summary",
		"mediaUrls",
		"coverUrl",
		"articleDocument",
		"articleTemplate",
		"articleFontPreset",
	} {
		if _, exists := payload[key]; exists {
			return rterr.NewInvalidArgument(
				rterr.ModuleContent,
				"发布后不可修改影响最终显示的文章内容",
				"published content is immutable",
			)
		}
	}
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
		if len(post.ArticleDocument) == 0 {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "文章内容不能为空", "article requires articleDocument")
		}
		hasBody := strings.TrimSpace(post.Body) != ""
		hasImages := len(asStringSlice(post.MediaUrls)) > 0
		hasTitle := strings.TrimSpace(post.Title) != ""
		if !hasBody && !hasImages && !hasTitle {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "文章内容不能为空", "article requires title, body or image")
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

type RequestOriginalImageAccessInput struct {
	MediaID   string
	Purpose   string
	ViewerID  string
	SessionID string
}

type OriginalImageAccessResponse struct {
	MediaID     string         `json:"mediaId"`
	Status      string         `json:"status"`
	OriginalURL string         `json:"originalUrl,omitempty"`
	Format      string         `json:"format,omitempty"`
	SizeBytes   int64          `json:"sizeBytes,omitempty"`
	Width       int64          `json:"width,omitempty"`
	Height      int64          `json:"height,omitempty"`
	ExpiresAt   *time.Time     `json:"expiresAt,omitempty"`
	TtlSeconds  int            `json:"ttlSeconds,omitempty"`
	Watermark   map[string]any `json:"watermark,omitempty"`
	AuditID     string         `json:"auditId,omitempty"`
}

func (s *PostService) UpdateMediaAssetAccessPolicy(mediaID string, patch map[string]any) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	asset, ok := s.mediaAssets[strings.TrimSpace(mediaID)]
	if !ok {
		return false
	}
	if asset.AccessPolicy == nil {
		asset.AccessPolicy = map[string]any{}
	}
	for key, value := range patch {
		asset.AccessPolicy[key] = value
	}
	asset.UpdatedAt = time.Now().UTC()
	s.mediaAssets[asset.ID] = asset
	return true
}

func (s *PostService) RequestOriginalImageAccess(ctx context.Context, in RequestOriginalImageAccessInput) (*OriginalImageAccessResponse, error) {
	mediaID := strings.TrimSpace(in.MediaID)
	if mediaID == "" {
		return nil, rterr.NewAppError(rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "media_not_found"), "媒体资源不存在或已过期", "missing mediaId")
	}
	purpose := strings.ToLower(strings.TrimSpace(in.Purpose))
	if purpose == "" {
		purpose = "view"
	}
	if purpose != "view" && purpose != "save" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "purpose 仅支持 view/save", "unsupported purpose: "+purpose)
	}
	s.mu.Lock()
	asset, ok := s.mediaAssets[mediaID]
	s.mu.Unlock()
	if !ok {
		return nil, rterr.NewAppError(rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "media_not_found"), "媒体资源不存在或已过期", "media not found")
	}
	if strings.ToLower(strings.TrimSpace(asset.Type)) != "image" && strings.ToLower(strings.TrimSpace(asset.Type)) != "video" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "原图/原视频申请仅支持图片或视频类型资产", "unsupported asset type")
	}
	if !originalAccessPolicyAllows(asset, purpose) {
		return nil, rterr.NewAppError(rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "original_access_denied"), "当前内容不支持查看或保存原图", "denied by policy")
	}
	now := time.Now().UTC()
	ttl := 300
	if raw, ok := asset.AccessPolicy["originalTtlSeconds"]; ok {
		if parsed := positiveIntFromAny(raw); parsed > 0 {
			ttl = parsed
		}
	}
	expiresAt := now.Add(time.Duration(ttl) * time.Second)
	base := strings.TrimSpace(asset.OriginUrl)
	if base == "" {
		base = strings.TrimSpace(asset.CdnUrl)
	}
	if base == "" {
		base = "https://cdn.example/media/" + mediaID
	}
	sep := "?"
	if strings.Contains(base, "?") {
		sep = "&"
	}
	signed := fmt.Sprintf("%s%sx-original=%s&x-purpose=%s&x-exp=%d&x-sig=%x", base, sep, mediaID, purpose, expiresAt.Unix(), len(base)+len(mediaID)+len(purpose))
	auditID := fmt.Sprintf("audit_orig_%d", now.UnixNano())
	if s.publisher != nil {
		_ = s.publisher.Publish(ctx, repository.DomainEvent{Type: "MediaOriginalAccessGranted", AggregateType: "MediaAsset", AggregateID: mediaID, Payload: map[string]any{"mediaId": mediaID, "purpose": purpose, "viewerId": in.ViewerID, "sessionId": in.SessionID, "auditId": auditID, "expiresAt": expiresAt.Format(time.RFC3339)}, OccurredAt: now.Format(time.RFC3339)})
	}
	return &OriginalImageAccessResponse{MediaID: mediaID, Status: "granted", OriginalURL: signed, Format: asset.MimeType, SizeBytes: asset.FileSizeBytes, Width: asset.Width, Height: asset.Height, ExpiresAt: &expiresAt, TtlSeconds: ttl, AuditID: auditID}, nil
}

func originalAccessPolicyAllows(asset postmodel.MediaAsset, purpose string) bool {
	if asset.AccessPolicy == nil {
		return true
	}
	if purpose == "save" {
		if v, ok := asset.AccessPolicy["allowOriginalSave"].(bool); ok {
			return v
		}
	}
	if purpose == "view" {
		if v, ok := asset.AccessPolicy["allowOriginalView"].(bool); ok {
			return v
		}
	}
	if v, ok := asset.AccessPolicy["originalAllowed"].(bool); ok {
		return v
	}
	return true
}

func positiveIntFromAny(v any) int {
	switch tv := v.(type) {
	case int:
		if tv > 0 {
			return tv
		}
	case int64:
		if tv > 0 {
			return int(tv)
		}
	case float64:
		if tv > 0 {
			return int(tv)
		}
	case string:
		if parsed, err := strconv.Atoi(strings.TrimSpace(tv)); err == nil && parsed > 0 {
			return parsed
		}
	}
	return 0
}
