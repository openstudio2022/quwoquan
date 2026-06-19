package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/url"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rterr "quwoquan_service/runtime/errors"
	runtimemedia "quwoquan_service/runtime/media"
	rtobs "quwoquan_service/runtime/observability"
	rtrec "quwoquan_service/runtime/recommendation"
	"quwoquan_service/runtime/repository"
	rtsearch "quwoquan_service/runtime/search"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	postsemantic "quwoquan_service/services/content-service/internal/domain/post/semantic"
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
	SemanticMentionPosts         int  `json:"semanticMentionPosts"`
	ActiveReferenceChanges       int  `json:"activeReferenceChanges"`
	InvalidPublishedMentions     int  `json:"invalidPublishedMentions"`
}

type SemanticMentionReprojectionReport struct {
	CandidateID            string `json:"candidateId"`
	Status                 string `json:"status"`
	MatchedPosts           int    `json:"matchedPosts"`
	UpdatedMentions        int    `json:"updatedMentions"`
	ActiveReferenceChanges int    `json:"activeReferenceChanges"`
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
	store            persistence.PostRepository
	signaler         rtrec.SignalProcessor
	publisher        repository.EventPublisher
	projector        Projector
	logger           *slog.Logger
	mu               sync.Mutex
	reactions        map[string]map[string]contentReactionState // postID -> userID -> state
	distributions    map[string]map[string]bool                 // postID -> circleID -> active
	reshares         map[string]map[string]bool                 // postID -> (circleID:userID) -> active
	tombstones       map[string]time.Time                       // postID -> deletedAt
	mediaAssets      map[string]postmodel.MediaAsset            // mediaID -> asset
	uploadSession    map[string]string                          // sessionID -> mediaID
	comments         map[string][]map[string]any                // postID -> comments list
	commentReactions map[string]map[string]string               // commentID -> userID -> like|dislike|none
	commentMaxLen    int                                        // configurable, default 500
	storyRuntime     StoryRuntimeConfig
	mediaCDNBase     string
	mediaUploadBase  string
	mediaStore       runtimemedia.MediaStore
}

func NewPostService(store persistence.PostRepository, opts ...PostServiceOption) *PostService {
	s := &PostService{
		store:            store,
		logger:           slog.Default(),
		reactions:        map[string]map[string]contentReactionState{},
		distributions:    map[string]map[string]bool{},
		reshares:         map[string]map[string]bool{},
		tombstones:       map[string]time.Time{},
		mediaAssets:      map[string]postmodel.MediaAsset{},
		uploadSession:    map[string]string{},
		comments:         map[string][]map[string]any{},
		commentReactions: map[string]map[string]string{},
		commentMaxLen:    500,
		storyRuntime:     defaultStoryRuntimeConfig(),
		mediaCDNBase:     "https://media.quwoquan.invalid",
		mediaUploadBase:  "https://media-origin.quwoquan.invalid",
		mediaStore:       runtimemedia.NewMockMediaStore(),
	}
	for _, opt := range opts {
		opt(s)
	}
	return s
}

type contentReactionState struct {
	Liked bool
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

func WithMediaURLConfig(cdnBaseURL, uploadBaseURL string) PostServiceOption {
	return func(s *PostService) {
		if normalized := normalizeHTTPSBaseURL(cdnBaseURL); normalized != "" {
			s.mediaCDNBase = normalized
		}
		if normalized := normalizeHTTPSBaseURL(uploadBaseURL); normalized != "" {
			s.mediaUploadBase = normalized
		}
	}
}

func WithMediaStore(store runtimemedia.MediaStore) PostServiceOption {
	return func(s *PostService) {
		s.mediaStore = store
	}
}

func normalizeHTTPSBaseURL(raw string) string {
	value := strings.TrimRight(strings.TrimSpace(raw), "/")
	if value == "" {
		return ""
	}
	parsed, err := url.Parse(value)
	if err != nil || parsed.Scheme != "https" || parsed.Host == "" {
		return ""
	}
	return value
}

func mediaFileExt(mediaType string) string {
	switch strings.ToLower(strings.TrimSpace(mediaType)) {
	case "video":
		return "mp4"
	case "audio":
		return "m4a"
	default:
		return "jpg"
	}
}

func mediaMimeType(mediaType string) string {
	switch strings.ToLower(strings.TrimSpace(mediaType)) {
	case "video":
		return "video/mp4"
	case "audio":
		return "audio/mp4"
	default:
		return "image/jpeg"
	}
}

func mediaObjectKey(scope, ownerID, sessionID, mediaID, mediaType string) string {
	normalizedScope := defaultString(strings.TrimSpace(scope), "draft")
	normalizedOwner := defaultString(strings.TrimSpace(ownerID), AnonymousFallbackSubAccountID)
	return fmt.Sprintf(
		"uploads/post/%s/%s/%s/%s/original.%s",
		normalizedScope,
		normalizedOwner,
		sessionID,
		mediaID,
		mediaFileExt(mediaType),
	)
}

func mediaURL(base, objectKey string) string {
	return strings.TrimRight(base, "/") + "/" + strings.TrimLeft(objectKey, "/")
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
	projectSemanticMentionRefs(&copy)
	return &copy
}

func projectSemanticMentionRefs(post *postmodel.Post) postsemantic.Projection {
	if post == nil || !postsemantic.Present(post.SemanticMentions) {
		return postsemantic.Projection{}
	}
	projection := postsemantic.Project(post.SemanticMentions)
	post.EntityRefs = append([]string(nil), projection.EntityRefs...)
	post.TagRefs = append([]string(nil), projection.TagRefs...)
	return projection
}

func applySemanticMentionPayload(post *postmodel.Post, payload map[string]any) error {
	if post == nil {
		return nil
	}
	if semanticMentions, exists := payload["semanticMentions"]; exists {
		post.SemanticMentions = semanticMentions
	}
	if err := postsemantic.ValidateSuppliedRefs(
		post.SemanticMentions,
		asStringSlice(payload["entityRefs"]),
		asStringSlice(payload["tagRefs"]),
	); err != nil {
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"活动实体或标签引用不合法",
			err.Error(),
		)
	}
	if postsemantic.Present(post.SemanticMentions) {
		projectSemanticMentionRefs(post)
		return nil
	}
	if err := postsemantic.RejectCandidateRefs(post.EntityRefs, post.TagRefs); err != nil {
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"候选对象不能作为活动引用",
			err.Error(),
		)
	}
	return nil
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

func (s *PostService) CreatePost(ctx context.Context, payload map[string]any) (result *postmodel.Post, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "content.CreatePost",
		attribute.String("content.type", strings.TrimSpace(asString(payload["contentType"]))))
	defer func() { rtobs.EndSpan(span, err) }()

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
		ID:       fmt.Sprintf("post_%d", now.UnixNano()),
		AuthorId: strings.TrimSpace(asString(payload["authorId"])),
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
		TagRefs:             asStringSlice(payload["tagRefs"]),
		EntityRefs:          asStringSlice(payload["entityRefs"]),
		SemanticMentions:    payload["semanticMentions"],
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
		ArticleMarkdown:     strings.TrimSpace(asString(payload["articleMarkdown"])),
		ArticleMarkdownVersion: defaultString(
			strings.TrimSpace(asString(payload["articleMarkdownVersion"])),
			"qwq-rich-md/1",
		),
		ArticleAssetManifest: asMap(payload["articleAssetManifest"]),
		ArticleRenderProfile: asMap(payload["articleRenderProfile"]),
		ArticleTemplate:      strings.TrimSpace(asString(payload["articleTemplate"])),
		ArticleFontPreset:    strings.TrimSpace(asString(payload["articleFontPreset"])),
		Status:               "draft",
		ModerationStatus:     "pending",
		CreatedAt:            now,
		UpdatedAt:            now,
	}
	normalizePostObjectAnchors(post, payload)
	if err := applySemanticMentionPayload(post, payload); err != nil {
		return nil, err
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
	s.syncArticleMarkdownSnapshot(post)
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
				"tagRefs":            post.TagRefs,
				"entityRefs":         post.EntityRefs,
				"semanticMentions":   post.SemanticMentions,
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
	if tags, exists := payload["tagRefs"]; exists {
		post.TagRefs = asStringSlice(tags)
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
	if articleMarkdown, exists := payload["articleMarkdown"]; exists {
		post.ArticleMarkdown = strings.TrimSpace(asString(articleMarkdown))
	}
	if articleMarkdownVersion, exists := payload["articleMarkdownVersion"]; exists {
		post.ArticleMarkdownVersion = defaultString(
			strings.TrimSpace(asString(articleMarkdownVersion)),
			"qwq-rich-md/1",
		)
	}
	if articleAssetManifest, exists := payload["articleAssetManifest"]; exists {
		post.ArticleAssetManifest = asMap(articleAssetManifest)
	}
	if articleRenderProfile, exists := payload["articleRenderProfile"]; exists {
		post.ArticleRenderProfile = asMap(articleRenderProfile)
	}
	normalizePostObjectAnchors(post, payload)
	if err := applySemanticMentionPayload(post, payload); err != nil {
		return nil, err
	}
	post.UpdatedAt = time.Now().UTC()
	s.syncArticleMarkdownSnapshot(post)
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

func (s *PostService) PublishPost(ctx context.Context, postID string, payload map[string]any) (result *postmodel.Post, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "content.PublishPost",
		attribute.String("post.id", postID))
	defer func() { rtobs.EndSpan(span, err) }()

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
				"tagRefs":            asStringSlice(post.TagRefs),
				"entityRefs":         asStringSlice(post.EntityRefs),
				"semanticMentions":   post.SemanticMentions,
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
				"tagRefs":            asStringSlice(post.TagRefs),
				"entityRefs":         asStringSlice(post.EntityRefs),
				"semanticMentions":   post.SemanticMentions,
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
	previousCircleIDs := asStringSlice(post.CircleIds)
	if err := applyPostSettingsPayload(post, payload); err != nil {
		return nil, err
	}
	addedCircleIDs, removedCircleIDs := diffCircleIDs(previousCircleIDs, asStringSlice(post.CircleIds))
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
		"addedCircleIds":     addedCircleIDs,
		"removedCircleIds":   removedCircleIDs,
		"assistantUsePolicy": post.AssistantUsePolicy,
		"publishedAt":        formatTimePtr(post.PublishedAt),
		"title":              post.Title,
		"tagRefs":            asStringSlice(post.TagRefs),
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
		"addedCircleIds":     addedCircleIDs,
		"removedCircleIds":   removedCircleIDs,
		"assistantUsePolicy": post.AssistantUsePolicy,
		"publishedAt":        formatTimePtr(post.PublishedAt),
		"title":              post.Title,
		"tagRefs":            asStringSlice(post.TagRefs),
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
	if tags, exists := payload["tagRefs"]; exists {
		post.TagRefs = asStringSlice(tags)
	}
	if entityRefs, exists := payload["entityRefs"]; exists {
		post.EntityRefs = asStringSlice(entityRefs)
	}
	if coverURL, exists := payload["coverUrl"]; exists {
		post.CoverUrl = strings.TrimSpace(asString(coverURL))
	}
	if articleMarkdown, exists := payload["articleMarkdown"]; exists {
		post.ArticleMarkdown = strings.TrimSpace(asString(articleMarkdown))
	}
	if articleMarkdownVersion, exists := payload["articleMarkdownVersion"]; exists {
		post.ArticleMarkdownVersion = defaultString(
			strings.TrimSpace(asString(articleMarkdownVersion)),
			"qwq-rich-md/1",
		)
	}
	if articleAssetManifest, exists := payload["articleAssetManifest"]; exists {
		post.ArticleAssetManifest = asMap(articleAssetManifest)
	}
	if articleRenderProfile, exists := payload["articleRenderProfile"]; exists {
		post.ArticleRenderProfile = asMap(articleRenderProfile)
	}
	normalizePostObjectAnchors(post, payload)
	if err := applySemanticMentionPayload(post, payload); err != nil {
		return nil, err
	}
	if err := applyPostSettingsPayload(post, promoteSettingsPayload(payload)); err != nil {
		return nil, err
	}
	s.syncArticleMarkdownSnapshot(post)
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
		"tagRefs":            asStringSlice(post.TagRefs),
		"entityRefs":         asStringSlice(post.EntityRefs),
		"semanticMentions":   post.SemanticMentions,
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
		"tagRefs":            asStringSlice(post.TagRefs),
		"entityRefs":         asStringSlice(post.EntityRefs),
		"semanticMentions":   post.SemanticMentions,
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
	statusBeforeDelete := post.Status
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
		"status":          statusBeforeDelete,
		"circleIds":       asStringSlice(post.CircleIds),
		"deletedAt":       post.DeletedAt.Format(time.RFC3339),
	}, now)
	s.projectPostEvent(ctx, "PostDeleted", post, map[string]any{
		"_id":             post.ID,
		"contentType":     post.ContentType,
		"contentIdentity": post.ContentIdentity,
		"status":          statusBeforeDelete,
		"circleIds":       asStringSlice(post.CircleIds),
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
	previousCircleIDs := asStringSlice(post.CircleIds)
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
	addedCircleIDs, removedCircleIDs := diffCircleIDs(previousCircleIDs, active)
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
		"addedCircleIds":     addedCircleIDs,
		"removedCircleIds":   removedCircleIDs,
		"assistantUsePolicy": post.AssistantUsePolicy,
		"publishedAt":        formatTimePtr(post.PublishedAt),
		"title":              post.Title,
		"tagRefs":            asStringSlice(post.TagRefs),
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
		"addedCircleIds":     addedCircleIDs,
		"removedCircleIds":   removedCircleIDs,
		"assistantUsePolicy": post.AssistantUsePolicy,
		"publishedAt":        formatTimePtr(post.PublishedAt),
		"title":              post.Title,
		"tagRefs":            asStringSlice(post.TagRefs),
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

// SharePost 写入权威分享记录（幂等）。actor 维度由 userID（账号）优先、否则
// deviceActorID（游客设备维度）解析；账号维度与设备维度独立累加、不并账。
func (s *PostService) SharePost(ctx context.Context, postID, userID, deviceActorID string) (int64, bool, bool, error) {
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
	actorKey := reactionActorKey(userID, deviceActorID)

	s.mu.Lock()
	shareCount, changed, shared := s.applyShareRecordLocked(
		ctx,
		post,
		directShareKey(actorKey),
		actorKey,
		true)
	s.mu.Unlock()
	return shareCount, changed, shared, nil
}

// UnsharePost 取消权威分享记录（幂等）。actor 维度解析与 SharePost 一致。
func (s *PostService) UnsharePost(ctx context.Context, postID, userID, deviceActorID string) (int64, bool, bool, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return 0, false, false, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	actorKey := reactionActorKey(userID, deviceActorID)

	s.mu.Lock()
	shareCount, changed, shared := s.applyShareRecordLocked(
		ctx,
		post,
		directShareKey(actorKey),
		actorKey,
		false)
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
		true)
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

func (s *PostService) InitMediaUpload(ctx context.Context, userID, mediaType, assetScope, sourceKind string) map[string]any {
	now := time.Now().UTC()
	if userID == "" {
		userID = AnonymousFallbackSubAccountID
	}
	mediaID := fmt.Sprintf("media_%d", now.UnixNano())
	sessionID := fmt.Sprintf("upload_%d", now.UnixNano())
	assetScope = defaultString(strings.TrimSpace(assetScope), "draft")
	mediaType = defaultString(strings.TrimSpace(mediaType), "image")
	objectKey := mediaObjectKey(assetScope, userID, sessionID, mediaID, mediaType)
	uploadURL := mediaURL(s.mediaUploadBase, "upload/"+objectKey)
	if s.mediaStore != nil {
		if session, err := s.mediaStore.InitUpload(ctx, runtimemedia.InitUploadOpts{
			Category:    runtimemedia.CategoryPost,
			OwnerID:     userID,
			FileName:    "original." + mediaFileExt(mediaType),
			ContentType: mediaMimeType(mediaType),
			FileSize:    1,
		}); err == nil && session != nil {
			sessionID = session.SessionID
			objectKey = session.OSSKey
			uploadURL = session.PresignURL
		}
	}
	asset := postmodel.MediaAsset{
		ID:               mediaID,
		OwnerId:          userID,
		AssetScope:       assetScope,
		Type:             mediaType,
		OriginUrl:        mediaURL(s.mediaUploadBase, objectKey),
		ObjectKey:        objectKey,
		Sha256:           "",
		SourceKind:       defaultString(strings.TrimSpace(sourceKind), "user_upload"),
		MimeType:         mediaMimeType(mediaType),
		Status:           "pending",
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
		"sessionId":          sessionID,
		"mediaId":            mediaID,
		"uploadUrl":          uploadURL,
		"presignUrl":         uploadURL,
		"objectKey":          objectKey,
		"temporaryObjectKey": objectKey,
		"uploaderId":         userID,
		"assetScope":         asset.AssetScope,
	}
}

func (s *PostService) CompleteMediaUpload(ctx context.Context, sessionID string) (*postmodel.MediaAsset, error) {
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
	if asset.ObjectKey == "" {
		asset.ObjectKey = mediaObjectKey(asset.AssetScope, asset.OwnerId, sessionID, mediaID, asset.Type)
	}
	asset.CdnUrl = mediaURL(s.mediaCDNBase, asset.ObjectKey)
	asset.ThumbnailUrl = asset.CdnUrl + "?variant=thumb"
	if s.mediaStore != nil {
		if mediaAsset, err := s.mediaStore.CompleteUpload(ctx, strings.TrimSpace(sessionID), runtimemedia.CompleteUploadOpts{
			DurationMs:     asset.DurationMs,
			Width:          int(asset.Width),
			Height:         int(asset.Height),
			Metadata:       map[string]any{"contentMediaId": mediaID},
			DeclaredSha256: asset.Sha256,
		}); err == nil && mediaAsset != nil {
			asset.ObjectKey = mediaAsset.OSSKey
			asset.CdnUrl = mediaAsset.CDNURL
			asset.OriginUrl = mediaAsset.CDNURL
			asset.Sha256 = strings.TrimSpace(mediaAsset.Sha256)
			if strings.TrimSpace(mediaAsset.AssetID) != "" {
				asset.SourceUrl = mediaAsset.AssetID
			}
			if mediaAsset.FileSize > 0 {
				asset.FileSizeBytes = mediaAsset.FileSize
			}
		}
	}
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
		asset.AccessPolicy = map[string]any{"originalAllowed": true, "allowOriginalView": true, "allowOriginalSave": true, "originalTtlSeconds": 300, "originalSizeBytes": asset.FileSizeBytes, "originalSha256": asset.Sha256}
		asset.OriginalAccess = map[string]any{"available": true, "requiresExplicitAction": true, "sizeBytes": asset.FileSizeBytes, "format": asset.MimeType, "ttlSeconds": 300}
	}
	asset.UpdatedAt = time.Now().UTC()
	s.mediaAssets[mediaID] = asset
	return &asset, nil
}

func (s *PostService) BindMediaAssetsToPost(_ context.Context, postID string, assetIDs []string) (map[string]any, error) {
	postID = strings.TrimSpace(postID)
	if postID == "" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "postId 不能为空", "missing postId")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	bound := []string{}
	for _, rawID := range assetIDs {
		assetID := strings.TrimSpace(rawID)
		if assetID == "" {
			continue
		}
		asset, ok := s.mediaAssets[assetID]
		if !ok {
			return nil, rterr.NewAppError(
				rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "media_not_found"),
				"素材不存在",
				"media asset not found",
			)
		}
		if asset.Status != "" && asset.Status != "ready" {
			return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "素材尚未就绪", "media asset not ready")
		}
		asset.PostId = postID
		asset.AssetScope = "published"
		asset.UpdatedAt = time.Now().UTC()
		s.mediaAssets[assetID] = asset
		bound = append(bound, assetID)
	}
	return map[string]any{
		"postId":        postID,
		"boundAssetIds": bound,
		"boundCount":    len(bound),
	}, nil
}

func (s *PostService) BindMediaAssetsToComment(_ context.Context, commentID, userID string, assetIDs []string) (map[string]any, error) {
	commentID = strings.TrimSpace(commentID)
	if commentID == "" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "commentId 不能为空", "missing commentId")
	}
	userID = strings.TrimSpace(userID)
	s.mu.Lock()
	defer s.mu.Unlock()

	var comment map[string]any
	var postID string
	for _, comments := range s.comments {
		for _, c := range comments {
			if cid, _ := c["_id"].(string); cid == commentID {
				comment = c
				postID = asString(c["postId"])
				break
			}
		}
		if comment != nil {
			break
		}
	}
	if comment == nil {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "comment_not_found"),
			"评论不存在",
			"comment not found",
		)
	}
	if authorID := strings.TrimSpace(asString(comment["authorId"])); userID != "" && authorID != "" && authorID != userID {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "comment_forbidden_update"),
			"无权更新此评论附件",
			"comment author mismatch",
		)
	}
	boundIDs, attachments, err := s.prepareCommentAttachmentsLocked(postID, asString(comment["authorId"]), assetIDs)
	if err != nil {
		return nil, err
	}
	comment["attachmentMediaIds"] = boundIDs
	comment["attachments"] = attachments
	return map[string]any{
		"commentId":     commentID,
		"boundAssetIds": boundIDs,
		"boundCount":    len(boundIDs),
		"attachments":   attachments,
	}, nil
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
	if ok {
		if strings.EqualFold(strings.TrimSpace(post.Status), "deleted") {
			return nil, false, true
		}
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
	ctx, span := rtobs.StartBusinessSpan(ctx, "content.GetPostForViewer",
		attribute.String("post.id", postID))
	defer func() { rtobs.EndSpan(span, nil) }()
	post, ok, deleted := s.GetPostOrTombstone(ctx, postID)
	if !ok {
		return nil, false, deleted, false
	}
	if !canViewPost(post, viewerID, viewerCircleIDs) {
		return nil, false, false, true
	}
	return post, true, false, false
}

// LikePost 点赞（幂等 upsert）。actor 维度由 userID（账号）优先、否则 deviceActorID
// （隐私安全派生设备标识，游客设备维度）解析；账号维度与设备维度独立计数、不并账。
func (s *PostService) LikePost(ctx context.Context, postID, userID, deviceActorID string) (int64, bool, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return 0, false, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	actorKey := reactionActorKey(userID, deviceActorID)

	s.mu.Lock()
	defer s.mu.Unlock()
	byPost, ok := s.reactions[post.ID]
	if !ok {
		byPost = map[string]contentReactionState{}
		s.reactions[post.ID] = byPost
	}
	state := byPost[actorKey]
	changed := !state.Liked
	if changed {
		state.Liked = true
		byPost[actorKey] = state
		post.LikeCount++
		post.UpdatedAt = time.Now().UTC()
		_ = s.store.Update(ctx, post.ID, post)
	}
	return post.LikeCount, changed, nil
}

// UnlikePost 取消点赞（幂等）。actor 维度解析与 LikePost 一致。
func (s *PostService) UnlikePost(ctx context.Context, postID, userID, deviceActorID string) (int64, bool, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return 0, false, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	actorKey := reactionActorKey(userID, deviceActorID)

	s.mu.Lock()
	defer s.mu.Unlock()
	byPost, ok := s.reactions[post.ID]
	if !ok {
		byPost = map[string]contentReactionState{}
		s.reactions[post.ID] = byPost
	}
	state := byPost[actorKey]
	changed := state.Liked
	if changed {
		state.Liked = false
		byPost[actorKey] = state
		if post.LikeCount > 0 {
			post.LikeCount--
		}
		post.UpdatedAt = time.Now().UTC()
		_ = s.store.Update(ctx, post.ID, post)
	}
	return post.LikeCount, changed, nil
}

// GetReactionState 读取当前 actor 的互动状态。actor 维度由 userID（账号）优先、
// 否则 deviceActorID（游客设备维度）解析，使游客也能读回自身设备态点赞/分享。
func (s *PostService) GetReactionState(postID, userID, deviceActorID string) (liked, shared bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	normalizedPostID := strings.TrimSpace(postID)
	actorKey := reactionActorKey(userID, deviceActorID)
	shared = hasActiveShareForUser(s.reshares[normalizedPostID], actorKey)
	byPost, ok := s.reactions[normalizedPostID]
	if !ok {
		return false, shared
	}
	state, ok := byPost[actorKey]
	if !ok {
		return false, shared
	}
	return state.Liked, shared
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
			items = append(items, buildProfileInteractionActivityView(profileInteractionProjectionInput{
				ActivityID:         fmt.Sprintf("like:%s:%s", postID, actorID),
				ActivityType:       "like",
				Direction:          direction,
				ActorID:            actorID,
				TargetSubAccountID: post.AuthorId,
				Post:               post,
				CreatedAt:          post.UpdatedAt,
			}))
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
			items = append(items, buildProfileInteractionActivityView(profileInteractionProjectionInput{
				ActivityID:         fmt.Sprintf("comment:%s", stringValue(comment["_id"])),
				ActivityType:       "comment",
				Direction:          direction,
				ActorID:            actorID,
				TargetSubAccountID: post.AuthorId,
				Post:               post,
				Comment:            comment,
				CreatedAt:          parseActivityTime(comment["createdAt"]),
			}))
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
			items = append(items, buildProfileInteractionActivityView(profileInteractionProjectionInput{
				ActivityID:         fmt.Sprintf("share:%s:%s", postID, actorID),
				ActivityType:       "share",
				Direction:          direction,
				ActorID:            actorID,
				TargetSubAccountID: post.AuthorId,
				Post:               post,
				CreatedAt:          post.UpdatedAt,
			}))
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

func parseActivityTime(raw any) time.Time {
	if s, ok := raw.(string); ok {
		if parsed, err := time.Parse(time.RFC3339, s); err == nil {
			return parsed
		}
	}
	return time.Now().UTC()
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
	attachmentMediaIDs []string,
	mentions []map[string]any,
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
	var parentCommentID string
	s.mu.Lock()
	if replyToCommentID != "" {
		foundReplyTarget := false
		for _, c := range s.comments[post.ID] {
			if cid, _ := c["_id"].(string); cid == replyToCommentID {
				replyToUserId, _ = c["authorId"].(string)
				foundReplyTarget = true
				parentCommentID, _ = c["parentCommentId"].(string)
				if parentCommentID == "" {
					parentCommentID = replyToCommentID
				}
				break
			}
		}
		if !foundReplyTarget {
			s.mu.Unlock()
			return nil, 0, rterr.NewAppError(
				rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "comment_not_found"),
				"回复目标不存在",
				"reply target comment not found",
			)
		}
		for _, c := range s.comments[post.ID] {
			if cid, _ := c["_id"].(string); cid == parentCommentID {
				rc := asInt64Flexible(c["replyCount"])
				c["replyCount"] = rc + 1
				break
			}
		}
	}
	attachmentIDs, attachments, err := s.prepareCommentAttachmentsLocked(post.ID, authorID, attachmentMediaIDs)
	if err != nil {
		s.mu.Unlock()
		return nil, 0, err
	}
	normalizedMentions := normalizeCommentMentions(mentions)
	assistantMentioned := commentHasAssistantMention(normalizedMentions)

	now := time.Now().UTC()
	post.CommentCount++
	post.UpdatedAt = now
	_ = s.store.Update(ctx, post.ID, post)

	isAuthor := authorID == post.AuthorId
	comment := map[string]any{
		"_id":      fmt.Sprintf("comment_%d", now.UnixNano()),
		"postId":   post.ID,
		"authorId": authorID,
		"personaContextVersion": asInt64Flexible(
			personaContextVersion,
		),
		"content":            content,
		"replyToCommentId":   replyToCommentID,
		"replyToUserId":      replyToUserId,
		"parentCommentId":    parentCommentID,
		"attachmentMediaIds": attachmentIDs,
		"attachments":        attachments,
		"mentions":           normalizedMentions,
		"assistantMentioned": assistantMentioned,
		"replyCount":         int64(0),
		"likeCount":          int64(0),
		"dislikeCount":       int64(0),
		"reportCount":        int64(0),
		"viewerReaction":     "none",
		"recommendedScore":   float64(0),
		"status":             "visible",
		"isAuthor":           isAuthor,
		"canDelete":          true,
		"canReply":           true,
		"canReport":          false,
		"createdAt":          now.Format(time.RFC3339),
		"deletedAt":          "",
	}
	s.comments[post.ID] = append(s.comments[post.ID], comment)
	projectedComment := s.projectCommentForViewerLocked(comment, authorID, true)
	s.mu.Unlock()

	if s.publisher != nil {
		featurePayload := commentFeaturePayload(*post, content, parentCommentID, replyToUserId, attachments)
		_ = s.publisher.Publish(ctx, repository.DomainEvent{
			Type:          "CommentCreated",
			AggregateType: "Post",
			AggregateID:   post.ID,
			Payload: map[string]any{
				"commentId":             comment["_id"],
				"postId":                post.ID,
				"authorId":              authorID,
				"content":               content,
				"commentLength":         len(contentRunes),
				"replyDepth":            commentReplyDepth(parentCommentID),
				"replyToUserId":         replyToUserId,
				"parentCommentId":       parentCommentID,
				"targetAuthorId":        featurePayload["targetAuthorId"],
				"attachmentMediaIds":    attachmentIDs,
				"attachmentTypes":       featurePayload["attachmentTypes"],
				"mentions":              normalizedMentions,
				"tagRefs":               featurePayload["tagRefs"],
				"entityRefs":            featurePayload["entityRefs"],
				"sentimentLabel":        featurePayload["sentimentLabel"],
				"intentLabel":           featurePayload["intentLabel"],
				"moderationLabels":      featurePayload["moderationLabels"],
				"intersectionDimension": featurePayload["intersectionDimension"],
			},
			OccurredAt: now.Format(time.RFC3339),
		})
	}

	return projectedComment, post.CommentCount, nil
}

func (s *PostService) ListComments(_ context.Context, postID, viewerID, cursor, sort string, limit int) ([]map[string]any, string, error) {
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
		if commentParentID(c) != "" {
			continue
		}
		active = append(active, c)
	}

	sortCommentsByMode(active, sort)

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
	projected := make([]map[string]any, 0, len(page))
	for _, c := range page {
		projected = append(projected, s.projectCommentForViewerLocked(c, viewerID, true))
	}
	return projected, nextCursor, nil
}

func (s *PostService) ListCommentReplies(_ context.Context, postID, commentID, viewerID, cursor string, limit int) ([]map[string]any, string, error) {
	if limit <= 0 {
		limit = 10
	}
	s.mu.Lock()
	defer s.mu.Unlock()

	parentID := strings.TrimSpace(commentID)
	all := s.comments[strings.TrimSpace(postID)]
	active := make([]map[string]any, 0, len(all))
	parentFound := false
	for _, c := range all {
		cid, _ := c["_id"].(string)
		if cid == parentID {
			parentFound = true
		}
		if del, _ := c["deletedAt"].(string); del != "" {
			continue
		}
		if commentParentID(c) == parentID {
			active = append(active, c)
		}
	}
	if !parentFound {
		return nil, "", rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "comment_not_found"),
			"评论不存在",
			"parent comment not found",
		)
	}
	sortCommentsByMode(active, "latest")
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
	projected := make([]map[string]any, 0, len(page))
	for _, c := range page {
		projected = append(projected, s.projectCommentForViewerLocked(c, viewerID, false))
	}
	return projected, nextCursor, nil
}

func sortCommentsByMode(comments []map[string]any, sortMode string) {
	mode := strings.TrimSpace(sortMode)
	if mode == "" {
		mode = "recommended"
	}
	sort.SliceStable(comments, func(i, j int) bool {
		left := comments[i]
		right := comments[j]
		switch mode {
		case "latest":
			return commentCreatedAt(left).After(commentCreatedAt(right))
		case "most_liked":
			if asInt64Flexible(left["likeCount"]) == asInt64Flexible(right["likeCount"]) {
				return commentCreatedAt(left).After(commentCreatedAt(right))
			}
			return asInt64Flexible(left["likeCount"]) > asInt64Flexible(right["likeCount"])
		default:
			leftScore := commentRecommendedScore(left)
			rightScore := commentRecommendedScore(right)
			if leftScore == rightScore {
				return commentCreatedAt(left).After(commentCreatedAt(right))
			}
			return leftScore > rightScore
		}
	})
}

func (s *PostService) syncArticleMarkdownSnapshot(post *postmodel.Post) {
	if post == nil || strings.TrimSpace(post.ContentType) != "article" {
		return
	}
	markdown := strings.TrimSpace(post.ArticleMarkdown)
	if markdown == "" {
		return
	}
	if strings.TrimSpace(post.ArticleMarkdownVersion) == "" {
		post.ArticleMarkdownVersion = "qwq-rich-md/1"
	}
	post.ArticleMarkdownDigest = markdownDigest(markdown)
	frontMatter, body := splitArticleMarkdownFrontMatter(markdown)
	if title := strings.TrimSpace(asString(frontMatter["title"])); title != "" {
		post.Title = title
	} else if strings.TrimSpace(post.Title) == "" {
		post.Title = firstMarkdownHeading(body)
	}
	if summary := strings.TrimSpace(asString(frontMatter["summary"])); summary != "" {
		post.Summary = summary
	}
	post.Body = markdownPlainText(body)
	if cover := strings.TrimSpace(asString(frontMatter["coverImage"])); cover != "" {
		post.CoverUrl = cover
	}
	if template := strings.TrimSpace(asString(frontMatter["template"])); template != "" {
		post.ArticleTemplate = template
	}
	if fontPreset := strings.TrimSpace(asString(frontMatter["fontPreset"])); fontPreset != "" {
		post.ArticleFontPreset = fontPreset
	}
	if len(post.ArticleRenderProfile) > 0 {
		if template := strings.TrimSpace(asString(post.ArticleRenderProfile["template"])); template != "" {
			post.ArticleTemplate = template
		}
		if fontPreset := strings.TrimSpace(asString(post.ArticleRenderProfile["fontPreset"])); fontPreset != "" {
			post.ArticleFontPreset = fontPreset
		}
	}
	post.MediaUrls = markdownAssetURIs(markdown)
}

func markdownDigest(markdown string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(markdown)))
	return "sha256:" + hex.EncodeToString(sum[:])
}

func splitArticleMarkdownFrontMatter(markdown string) (map[string]any, string) {
	normalized := strings.ReplaceAll(markdown, "\r\n", "\n")
	if !strings.HasPrefix(normalized, "---\n") {
		return nil, normalized
	}
	end := strings.Index(normalized[4:], "\n---")
	if end < 0 {
		return nil, normalized
	}
	raw := normalized[4 : 4+end]
	body := strings.TrimLeft(normalized[4+end+len("\n---"):], "\n")
	return parseSimpleFrontMatter(raw), body
}

func parseSimpleFrontMatter(raw string) map[string]any {
	result := map[string]any{}
	var currentListKey string
	for _, line := range strings.Split(raw, "\n") {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" {
			continue
		}
		if strings.HasPrefix(trimmed, "- ") && currentListKey != "" {
			result[currentListKey] = append(asStringSlice(result[currentListKey]), strings.TrimSpace(strings.TrimPrefix(trimmed, "- ")))
			continue
		}
		parts := strings.SplitN(trimmed, ":", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		value := strings.TrimSpace(parts[1])
		if value == "" {
			currentListKey = key
			result[key] = []string{}
			continue
		}
		currentListKey = ""
		result[key] = strings.Trim(value, `"'`)
	}
	return result
}

func firstMarkdownHeading(body string) string {
	for _, line := range strings.Split(body, "\n") {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "# ") {
			return strings.TrimSpace(strings.TrimPrefix(trimmed, "# "))
		}
	}
	return ""
}

func markdownPlainText(body string) string {
	lines := []string{}
	inFence := false
	for _, line := range strings.Split(body, "\n") {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "```") {
			inFence = !inFence
			continue
		}
		if inFence || trimmed == "" || strings.HasPrefix(trimmed, ":::") {
			continue
		}
		if strings.HasPrefix(trimmed, "#") {
			continue
		}
		if strings.HasPrefix(trimmed, "asset://") || strings.HasPrefix(trimmed, "![") {
			continue
		}
		lines = append(lines, strings.TrimPrefix(trimmed, "> "))
	}
	return strings.Join(lines, "\n")
}

func markdownAssetURIs(markdown string) []string {
	matches := regexp.MustCompile(`asset://[A-Za-z0-9_\-./]+`).FindAllString(markdown, -1)
	seen := map[string]bool{}
	result := []string{}
	for _, match := range matches {
		if !seen[match] {
			seen[match] = true
			result = append(result, match)
		}
	}
	return result
}

func commentRecommendedScore(c map[string]any) float64 {
	if score, ok := c["recommendedScore"].(float64); ok && score != 0 {
		return score
	}
	likes := asInt64Flexible(c["likeCount"])
	dislikes := asInt64Flexible(c["dislikeCount"])
	reports := asInt64Flexible(c["reportCount"])
	replies := asInt64Flexible(c["replyCount"])
	ageHours := time.Since(commentCreatedAt(c)).Hours()
	freshness := 24.0 - ageHours
	if freshness < 0 {
		freshness = 0
	}
	return float64(likes)*10 - float64(dislikes)*8 - float64(reports)*20 + float64(replies)*5 + freshness
}

func commentCreatedAt(c map[string]any) time.Time {
	if t, err := time.Parse(time.RFC3339, strings.TrimSpace(asString(c["createdAt"]))); err == nil {
		return t
	}
	return time.Time{}
}

func commentParentID(c map[string]any) string {
	parentID := strings.TrimSpace(asString(c["parentCommentId"]))
	if parentID != "" {
		return parentID
	}
	if replyToID := strings.TrimSpace(asString(c["replyToCommentId"])); replyToID != "" {
		return replyToID
	}
	return ""
}

func commentReplyDepth(parentCommentID string) int {
	if strings.TrimSpace(parentCommentID) == "" {
		return 0
	}
	return 1
}

func normalizeCommentMentions(mentions []map[string]any) []map[string]any {
	normalized := make([]map[string]any, 0, len(mentions))
	for _, mention := range mentions {
		targetID := strings.TrimSpace(asString(mention["targetId"]))
		if targetID == "" {
			targetID = strings.TrimSpace(asString(mention["userId"]))
		}
		displayName := strings.TrimSpace(asString(mention["displayName"]))
		mentionType := strings.TrimSpace(asString(mention["type"]))
		if mentionType == "" {
			mentionType = "user"
		}
		if targetID == "" && displayName == "" {
			continue
		}
		normalized = append(normalized, map[string]any{
			"type":        mentionType,
			"targetId":    targetID,
			"displayName": displayName,
		})
	}
	return normalized
}

func commentHasAssistantMention(mentions []map[string]any) bool {
	for _, mention := range mentions {
		mentionType := strings.TrimSpace(asString(mention["type"]))
		targetID := strings.TrimSpace(asString(mention["targetId"]))
		displayName := strings.TrimSpace(asString(mention["displayName"]))
		if strings.EqualFold(mentionType, "assistant") || strings.EqualFold(targetID, "assistant_xiaoqu") || strings.Contains(displayName, "小趣") {
			return true
		}
	}
	return false
}

func commentFeaturePayload(post postmodel.Post, content, parentCommentID, replyToUserID string, attachments []map[string]any) map[string]any {
	attachmentTypes := make([]string, 0, len(attachments))
	for _, attachment := range attachments {
		if mediaType := strings.TrimSpace(asString(attachment["type"])); mediaType != "" {
			attachmentTypes = append(attachmentTypes, mediaType)
		}
	}
	targetAuthorID := strings.TrimSpace(replyToUserID)
	if targetAuthorID == "" {
		targetAuthorID = post.AuthorId
	}
	return map[string]any{
		"targetAuthorId":        targetAuthorID,
		"attachmentTypes":       attachmentTypes,
		"tagRefs":               append([]string{}, post.TagRefs...),
		"entityRefs":            append([]string{}, post.EntityRefs...),
		"sentimentLabel":        classifyCommentSentiment(content),
		"intentLabel":           classifyCommentIntent(content),
		"moderationLabels":      []string{"pending"},
		"intersectionDimension": commentIntersectionDimension(post, parentCommentID),
	}
}

func classifyCommentSentiment(content string) string {
	text := strings.TrimSpace(content)
	switch {
	case strings.Contains(text, "喜欢") || strings.Contains(text, "漂亮") || strings.Contains(text, "赞"):
		return "positive"
	case strings.Contains(text, "不喜欢") || strings.Contains(text, "差") || strings.Contains(text, "踩"):
		return "negative"
	default:
		return "neutral"
	}
}

func classifyCommentIntent(content string) string {
	text := strings.TrimSpace(content)
	switch {
	case strings.Contains(text, "?") || strings.Contains(text, "？"):
		return "question"
	case strings.Contains(text, "@"):
		return "mention"
	default:
		return "discussion"
	}
}

func commentIntersectionDimension(post postmodel.Post, parentCommentID string) string {
	if strings.TrimSpace(parentCommentID) != "" {
		return "reply_edge"
	}
	if len(post.EntityRefs) > 0 {
		return "entity_interest"
	}
	if len(post.TagRefs) > 0 {
		return "tag_interest"
	}
	return "content_interest"
}

func commentReactionStrength(reaction string) float64 {
	switch strings.TrimSpace(reaction) {
	case "like":
		return 1
	case "dislike":
		return -1
	default:
		return 0
	}
}

func (s *PostService) prepareCommentAttachmentsLocked(postID, authorID string, assetIDs []string) ([]string, []map[string]any, error) {
	boundIDs := []string{}
	attachments := []map[string]any{}
	for _, rawID := range assetIDs {
		assetID := strings.TrimSpace(rawID)
		if assetID == "" {
			continue
		}
		asset, ok := s.mediaAssets[assetID]
		if !ok {
			return nil, nil, rterr.NewAppError(
				rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "media_not_found"),
				"素材不存在",
				"comment media asset not found",
			)
		}
		if asset.Status != "" && asset.Status != "ready" {
			return nil, nil, rterr.NewInvalidArgument(rterr.ModuleContent, "素材尚未就绪", "comment media asset not ready")
		}
		asset.PostId = strings.TrimSpace(postID)
		asset.OwnerId = defaultString(strings.TrimSpace(asset.OwnerId), strings.TrimSpace(authorID))
		asset.AssetScope = "comment"
		asset.UpdatedAt = time.Now().UTC()
		s.mediaAssets[assetID] = asset
		boundIDs = append(boundIDs, assetID)
		attachments = append(attachments, commentAttachmentSnapshot(asset))
	}
	return boundIDs, attachments, nil
}

func commentAttachmentSnapshot(asset postmodel.MediaAsset) map[string]any {
	url := strings.TrimSpace(asset.CdnUrl)
	if url == "" {
		url = strings.TrimSpace(asset.OriginUrl)
	}
	return map[string]any{
		"mediaId":      asset.ID,
		"type":         asset.Type,
		"url":          url,
		"thumbnailUrl": asset.ThumbnailUrl,
		"width":        asset.Width,
		"height":       asset.Height,
		"status":       asset.Status,
	}
}

func (s *PostService) projectCommentForViewerLocked(c map[string]any, viewerID string, includePreview bool) map[string]any {
	projected := map[string]any{}
	for k, v := range c {
		projected[k] = v
	}
	commentID := strings.TrimSpace(asString(c["_id"]))
	authorID := strings.TrimSpace(asString(c["authorId"]))
	viewerID = strings.TrimSpace(viewerID)
	reaction := "none"
	if byUser := s.commentReactions[commentID]; byUser != nil {
		if v := strings.TrimSpace(byUser[viewerID]); v == "like" || v == "dislike" {
			reaction = v
		}
	}
	projected["viewerReaction"] = reaction
	projected["likeCount"] = asInt64Flexible(c["likeCount"])
	projected["dislikeCount"] = asInt64Flexible(c["dislikeCount"])
	projected["replyCount"] = asInt64Flexible(c["replyCount"])
	projected["recommendedScore"] = commentRecommendedScore(c)
	projected["isAuthor"] = viewerID != "" && viewerID == authorID
	projected["canDelete"] = viewerID != "" && viewerID == authorID
	projected["canReply"] = strings.TrimSpace(asString(c["status"])) != "deleted"
	projected["canReport"] = viewerID != "" && viewerID != authorID
	if post, ok := s.store.FindByID(context.Background(), strings.TrimSpace(asString(c["postId"]))); ok {
		projected["postSummary"] = map[string]any{
			"postId":      post.ID,
			"contentType": post.ContentType,
			"title":       defaultString(strings.TrimSpace(post.Title), strings.TrimSpace(post.Summary)),
			"coverUrl":    post.CoverUrl,
			"status":      post.Status,
			"visibility":  post.Visibility,
			"authorId":    post.AuthorId,
		}
	}
	if !includePreview {
		projected["replyPreview"] = []map[string]any{}
		projected["replyNextCursor"] = ""
		return projected
	}
	parentID := commentID
	replies := make([]map[string]any, 0, 1)
	for _, candidate := range s.comments[strings.TrimSpace(asString(c["postId"]))] {
		if del, _ := candidate["deletedAt"].(string); del != "" {
			continue
		}
		if commentParentID(candidate) == parentID {
			replies = append(replies, candidate)
		}
	}
	sortCommentsByMode(replies, "latest")
	preview := []map[string]any{}
	for i, reply := range replies {
		if i >= 1 {
			break
		}
		preview = append(preview, s.projectCommentForViewerLocked(reply, viewerID, false))
	}
	projected["replyPreview"] = preview
	if len(replies) > len(preview) && len(preview) > 0 {
		projected["replyNextCursor"] = asString(preview[len(preview)-1]["_id"])
	} else {
		projected["replyNextCursor"] = ""
	}
	return projected
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
				"commentId":   commentID,
				"postId":      postID,
				"operatorId":  strings.TrimSpace(userID),
				"auditAction": "delete",
				"auditedAt":   time.Now().UTC().Format(time.RFC3339),
			},
			OccurredAt: time.Now().UTC().Format(time.RFC3339),
		})
	}
	return nil
}

func (s *PostService) ReactToComment(ctx context.Context, commentID, userID, reaction string) (map[string]any, error) {
	userID = strings.TrimSpace(userID)
	if userID == "" {
		userID = AnonymousFallbackSubAccountID
	}
	commentID = strings.TrimSpace(commentID)
	reaction = strings.TrimSpace(reaction)
	if reaction == "" {
		reaction = "none"
	}
	if reaction != "like" && reaction != "dislike" && reaction != "none" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "reaction 必须为 like/dislike/none", "invalid comment reaction")
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	var updated map[string]any
	var postID string
	var authorID string
	for _, comments := range s.comments {
		for _, c := range comments {
			if cid, _ := c["_id"].(string); cid == commentID {
				previous := "none"
				if byUser := s.commentReactions[commentID]; byUser != nil {
					if v := strings.TrimSpace(byUser[userID]); v == "like" || v == "dislike" {
						previous = v
					}
				}
				likeCount := asInt64Flexible(c["likeCount"])
				dislikeCount := asInt64Flexible(c["dislikeCount"])
				if previous == "like" && likeCount > 0 {
					likeCount--
				}
				if previous == "dislike" && dislikeCount > 0 {
					dislikeCount--
				}
				if reaction == "like" {
					likeCount++
				}
				if reaction == "dislike" {
					dislikeCount++
				}
				c["likeCount"] = likeCount
				c["dislikeCount"] = dislikeCount
				c["recommendedScore"] = commentRecommendedScore(c)
				byUser := s.commentReactions[commentID]
				if byUser == nil {
					byUser = map[string]string{}
					s.commentReactions[commentID] = byUser
				}
				if reaction == "none" {
					delete(byUser, userID)
				} else {
					byUser[userID] = reaction
				}
				postID = asString(c["postId"])
				authorID = asString(c["authorId"])
				updated = s.projectCommentForViewerLocked(c, userID, false)
				break
			}
		}
		if updated != nil {
			break
		}
	}
	if updated == nil {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "comment_not_found"),
			"评论不存在",
			"comment not found",
		)
	}
	if s.publisher != nil {
		var featurePayload map[string]any
		if post, ok := s.store.FindByID(ctx, postID); ok {
			featurePayload = commentFeaturePayload(*post, "", "", authorID, nil)
		} else {
			featurePayload = map[string]any{}
		}
		_ = s.publisher.Publish(ctx, repository.DomainEvent{
			Type:          "CommentReacted",
			AggregateType: "Post",
			AggregateID:   postID,
			Payload: map[string]any{
				"commentId":             commentID,
				"postId":                postID,
				"authorId":              authorID,
				"targetAuthorId":        featurePayload["targetAuthorId"],
				"userId":                userID,
				"viewerReaction":        reaction,
				"reactionStrength":      commentReactionStrength(reaction),
				"likeCount":             updated["likeCount"],
				"dislikeCount":          updated["dislikeCount"],
				"recommendedScore":      updated["recommendedScore"],
				"tagRefs":               featurePayload["tagRefs"],
				"entityRefs":            featurePayload["entityRefs"],
				"moderationLabels":      featurePayload["moderationLabels"],
				"intersectionDimension": featurePayload["intersectionDimension"],
			},
			OccurredAt: time.Now().UTC().Format(time.RFC3339),
		})
	}
	return updated, nil
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
	projected := make([]map[string]any, 0, len(page))
	for _, c := range page {
		projected = append(projected, s.projectCommentForViewerLocked(c, userID, false))
	}
	return projected, nextCursor, nil
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
	projected := make([]map[string]any, 0, len(page))
	for _, c := range page {
		projected = append(projected, s.projectCommentForViewerLocked(c, userID, false))
	}
	return projected, nextCursor, nil
}

func (s *PostService) GetAppConfig() map[string]any {
	runtimeConfig := normalizeStoryRuntimeConfig(s.storyRuntime)
	canaryMatrix := make([]any, 0, len(runtimeConfig.CanaryMatrix))
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
	payload := map[string]any{
		"schemaVersion":  "app_remote_config.v1",
		"packageVersion": "embedded-content-service",
		"fetchedAt":      time.Now().UTC().Format(time.RFC3339),
		"maxAgeSec":      21600,
		"activationPolicy": map[string]any{
			"default":       "next_session",
			"kill_switches": "immediate",
		},
		"content": map[string]any{
			"comment": map[string]any{
				"max_length":             s.commentMaxLen,
				"reply_preview_count":    3,
				"reply_expand_page_size": 10,
				"fold_line_count":        3,
				"attachment":             map[string]any{"max_images": 1},
			},
			"feature_flags": featureFlags,
			"gray_release": map[string]any{
				"experiment_bucket": runtimeConfig.ExperimentBucket,
				"current_stage":     runtimeConfig.CurrentStage,
				"canary_matrix":     canaryMatrix,
			},
		},
	}
	payload["configHash"] = appConfigHash(payload)
	return payload
}

func appConfigHash(payload map[string]any) string {
	clone := map[string]any{}
	for key, value := range payload {
		if key == "configHash" || key == "fetchedAt" {
			continue
		}
		clone[key] = value
	}
	data, _ := json.Marshal(clone)
	sum := sha256.Sum256(data)
	return "sha256:" + hex.EncodeToString(sum[:])
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
		"like":    post.LikeCount,
		"comment": post.CommentCount,
		"share":   post.ShareCount,
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
	ctx, span := rtobs.StartBusinessSpan(ctx, "content.SearchPosts",
		attribute.String("search.query", req.Query),
		attribute.String("search.identity", req.Identity),
		attribute.String("search.requested_type", req.RequestedType))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	limit := req.Limit
	if limit <= 0 {
		limit = 20
	}
	query := strings.TrimSpace(strings.ToLower(req.Query))
	expectedIdentity := normalizeRequestedIdentity(req.Identity)
	expectedType := normalizeRequestType(req.RequestedType)
	posts := s.store.ListPublished(ctx, limit*8, req.Cursor)
	type indexedPost struct {
		post        postmodel.Post
		categoryID  string
		subCategory string
		summary     string
		coverURL    string
	}
	index := map[string]indexedPost{}
	docs := make([]rtsearch.Document, 0, len(posts))
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
		summary := strings.TrimSpace(post.Summary)
		if summary == "" {
			summary = strings.TrimSpace(post.Body)
		}
		coverURL := strings.TrimSpace(post.CoverUrl)
		if coverURL == "" {
			coverURL = strings.TrimSpace(post.VideoUrl)
		}
		categoryID, subCategory := deriveSearchTopicCategories(
			asStringSlice(post.TagRefs),
			req.CategoryID,
			req.SubCategory,
		)
		index[post.ID] = indexedPost{
			post:        post,
			categoryID:  categoryID,
			subCategory: subCategory,
			summary:     summary,
			coverURL:    coverURL,
		}
		visibility := strings.TrimSpace(post.Visibility)
		if visibility == "" {
			visibility = "public"
		}
		docs = append(docs, rtsearch.Document{
			ObjectType:   rtsearch.ObjectTypeContentPost,
			ObjectID:     post.ID,
			Title:        post.Title,
			Summary:      strings.TrimSpace(post.Summary),
			Body:         post.Body,
			SourceDomain: "content",
			ContentType:  post.ContentType,
			Visibility:   visibility,
			BadgeLabel:   "内容",
			Popularity:   float64(post.LikeCount + post.CommentCount + post.ShareCount),
			Freshness:    post.PublishedAt,
			Fields: map[string]string{
				"tagRefs":           strings.Join(asStringSlice(post.TagRefs), " "),
				"entityRefs":        strings.Join(asStringSlice(post.EntityRefs), " "),
				"authorDisplayName": post.AuthorDisplayNameSnapshot,
				"locationName":      post.LocationName,
			},
		})
	}
	searchResp := rtsearch.Execute(rtsearch.Request{
		Query:       query,
		Mode:        rtsearch.ModeResult,
		ObjectTypes: []string{rtsearch.ObjectTypeContentPost},
		Limit:       limit,
	}, docs)
	results := make([]postmodel.PostSearchItemView, 0, len(searchResp.Hits))
	for _, hit := range searchResp.Hits {
		item, ok := index[hit.ObjectID]
		if !ok {
			continue
		}
		post := item.post
		primaryCircleID := strings.TrimSpace(post.CircleId)
		if primaryCircleID == "" {
			circleIDs := asStringSlice(post.CircleIds)
			if len(circleIDs) > 0 {
				primaryCircleID = strings.TrimSpace(circleIDs[0])
			}
		}
		results = append(results, postmodel.PostSearchItemView{
			PostId:            post.ID,
			ContentType:       post.ContentType,
			ContentIdentity:   post.ContentIdentity,
			Title:             post.Title,
			Summary:           item.summary,
			CoverUrl:          item.coverURL,
			AuthorId:          post.AuthorId,
			AuthorDisplayName: post.AuthorDisplayNameSnapshot,
			AuthorAvatarUrl:   post.AuthorAvatarUrlSnapshot,
			CircleId:          primaryCircleID,
			CircleName:        "",
			CategoryId:        item.categoryID,
			SubCategory:       item.subCategory,
			LikeCount:         post.LikeCount,
			HighlightText:     hit.Snippet,
			MatchedField:      hit.MatchedField,
			PublishedAt:       post.PublishedAt,
		})
	}
	nextCursor := ""
	if len(results) == limit {
		nextCursor = results[len(results)-1].PostId
	}
	return results, nextCursor, nil
}

func deriveSearchTopicCategories(tagRefs []string, fallbackCategory string, fallbackSubCategory string) (string, string) {
	topics := make([]string, 0, 2)
	seen := map[string]struct{}{}
	addTopic := func(value string) {
		value = strings.TrimSpace(value)
		if value == "" {
			return
		}
		if _, ok := seen[value]; ok {
			return
		}
		seen[value] = struct{}{}
		topics = append(topics, value)
	}
	for _, raw := range tagRefs {
		tag := strings.Trim(strings.TrimSpace(raw), "/")
		if tag == "" {
			continue
		}
		parts := strings.Split(tag, "/")
		if len(parts) < 2 || !strings.EqualFold(strings.TrimSpace(parts[0]), "Topic") {
			continue
		}
		for _, part := range parts[1:] {
			addTopic(part)
			if len(topics) >= 2 {
				break
			}
		}
		if len(topics) >= 2 {
			break
		}
	}
	category := strings.TrimSpace(fallbackCategory)
	subCategory := strings.TrimSpace(fallbackSubCategory)
	if len(topics) > 0 {
		category = topics[0]
	}
	if len(topics) > 1 {
		subCategory = topics[1]
	}
	return category, subCategory
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
		rawEntityRefs := append([]string(nil), stored.EntityRefs...)
		rawTagRefs := append([]string(nil), stored.TagRefs...)
		post := normalizePostForRead(&stored)
		if post == nil {
			continue
		}
		if postsemantic.Present(stored.SemanticMentions) {
			report.SemanticMentionPosts++
			projection := postsemantic.Project(stored.SemanticMentions)
			report.InvalidPublishedMentions += projection.InvalidPublishedCount
			if !sameStringSet(rawEntityRefs, post.EntityRefs) || !sameStringSet(rawTagRefs, post.TagRefs) {
				report.ActiveReferenceChanges++
			}
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
		if postsemantic.Present(stored.SemanticMentions) &&
			(!sameStringSet(rawEntityRefs, post.EntityRefs) || !sameStringSet(rawTagRefs, post.TagRefs)) {
			post.UpdatedAt = now
			if !s.store.Update(ctx, post.ID, post) {
				return report, rterr.NewAppError(
					rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "update_failed"),
					"语义引用回填失败",
					"post disappeared while rebuilding semantic mention projection",
				)
			}
		}
		eventType := projectionEventTypeForPost(post)
		s.projectPostEvent(ctx, eventType, post, projectionPayloadForPost(post), now)
	}
	return report, nil
}

func (s *PostService) ApplySemanticMentionGovernanceEvent(
	ctx context.Context,
	event postsemantic.GovernanceEvent,
) (SemanticMentionReprojectionReport, error) {
	report := SemanticMentionReprojectionReport{
		CandidateID: strings.TrimSpace(event.CandidateID),
		Status:      strings.ToLower(strings.TrimSpace(event.Status)),
	}
	if err := postsemantic.ValidateGovernanceEvent(event); err != nil {
		return report, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"语义标注治理事件不合法",
			err.Error(),
		)
	}

	now := time.Now().UTC()
	for _, stored := range s.store.ListAll(ctx) {
		updatedMentions, updatedCount, err := postsemantic.ApplyGovernanceEvent(
			stored.SemanticMentions,
			event,
		)
		if err != nil {
			return report, err
		}
		if updatedCount == 0 {
			continue
		}
		report.MatchedPosts++
		report.UpdatedMentions += updatedCount

		post := stored
		beforeEntityRefs := append([]string(nil), post.EntityRefs...)
		beforeTagRefs := append([]string(nil), post.TagRefs...)
		post.SemanticMentions = updatedMentions
		projectSemanticMentionRefs(&post)
		if !sameStringSet(beforeEntityRefs, post.EntityRefs) || !sameStringSet(beforeTagRefs, post.TagRefs) {
			report.ActiveReferenceChanges++
		}
		post.UpdatedAt = now
		if !s.store.Update(ctx, post.ID, &post) {
			return report, rterr.NewAppError(
				rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "update_failed"),
				"语义标注回填失败",
				"post disappeared while applying semantic mention governance event",
			)
		}

		payload := projectionPayloadForPost(&post)
		s.publishPostEvent(ctx, "PostUpdated", &post, payload, now)
		s.projectPostEvent(ctx, projectionEventTypeForPost(&post), &post, payload, now)
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

func diffCircleIDs(before []string, after []string) ([]string, []string) {
	beforeSet := normalizedStringSet(before)
	afterSet := normalizedStringSet(after)
	added := make([]string, 0)
	removed := make([]string, 0)
	for id := range afterSet {
		if !beforeSet[id] {
			added = append(added, id)
		}
	}
	for id := range beforeSet {
		if !afterSet[id] {
			removed = append(removed, id)
		}
	}
	sort.Strings(added)
	sort.Strings(removed)
	return added, removed
}

func normalizedStringSet(values []string) map[string]bool {
	out := make(map[string]bool, len(values))
	for _, value := range values {
		if id := strings.TrimSpace(value); id != "" {
			out[id] = true
		}
	}
	return out
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
		"createdAt":          formatTimePtr(post.CreatedAt),
		"updatedAt":          formatTimePtr(post.UpdatedAt),
		"title":              post.Title,
		"summary":            post.Summary,
		"coverUrl":           post.CoverUrl,
		"semanticMentions":   post.SemanticMentions,
		"tagRefs":            asStringSlice(post.TagRefs),
		"entityRefs":         asStringSlice(post.EntityRefs),
		"primaryHomepageId":  strings.TrimSpace(post.PrimaryHomepageId),
		"canonicalEntityId":  strings.TrimSpace(post.CanonicalEntityId),
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
	tags := asStringSlice(p.TagRefs)
	if len(tags) == 0 && p.ContentType != "" {
		tags = []string{p.ContentType}
	}
	return tags
}

func normalizePostObjectAnchors(post *postmodel.Post, payload map[string]any) {
	if post == nil {
		return
	}
	if primaryHomepageID, exists := payload["primaryHomepageId"]; exists {
		post.PrimaryHomepageId = strings.TrimSpace(asString(primaryHomepageID))
	}
	if primaryHomepageType, exists := payload["primaryHomepageType"]; exists {
		post.PrimaryHomepageType = strings.TrimSpace(asString(primaryHomepageType))
	}
	if primaryHomepageSnapshot, exists := payload["primaryHomepageSnapshot"]; exists {
		post.PrimaryHomepageSnapshot = asMap(primaryHomepageSnapshot)
	}
	if entityRefs, exists := payload["entityRefs"]; exists {
		post.EntityRefs = normalizeRuntimeEntityRefs(asStringSlice(entityRefs))
	} else {
		post.EntityRefs = normalizeRuntimeEntityRefs(post.EntityRefs)
	}
	if canonicalEntityID := strings.TrimSpace(canonicalEntityIDFromPayload(payload)); canonicalEntityID != "" {
		post.CanonicalEntityId = canonicalEntityID
	} else if canonicalEntityID := strings.TrimSpace(canonicalEntityIDFromHomepage(post.PrimaryHomepageId, post.PrimaryHomepageType)); canonicalEntityID != "" {
		post.CanonicalEntityId = canonicalEntityID
	} else {
		post.CanonicalEntityId = strings.TrimSpace(post.CanonicalEntityId)
	}
	if post.CanonicalEntityId != "" && !containsString(post.EntityRefs, post.CanonicalEntityId) {
		post.EntityRefs = append([]string{post.CanonicalEntityId}, post.EntityRefs...)
	}
}

func canonicalEntityIDFromPayload(payload map[string]any) string {
	if payload == nil {
		return ""
	}
	if explicit := strings.TrimSpace(asString(payload["canonicalEntityId"])); explicit != "" {
		return explicit
	}
	snapshot := asMap(payload["primaryHomepageSnapshot"])
	return strings.TrimSpace(asString(snapshot["canonicalEntityId"]))
}

func canonicalEntityIDFromHomepage(homepageID, homepageType string) string {
	id := strings.TrimSpace(homepageID)
	if id == "" {
		return ""
	}
	normalizedType := strings.TrimSpace(homepageType)
	if normalizedType == "" {
		normalizedType = inferHomepageTypeFromID(id)
	}
	if normalizedType == "" {
		return ""
	}
	trimmedID := strings.TrimSpace(strings.TrimPrefix(id, "homepage_"))
	prefix := normalizedType + "_"
	if strings.HasPrefix(trimmedID, prefix) {
		trimmedID = strings.TrimPrefix(trimmedID, prefix)
	}
	trimmedID = strings.Trim(trimmedID, "_")
	if trimmedID == "" {
		return ""
	}
	return "entity:" + normalizedType + ":" + trimmedID
}

func inferHomepageTypeFromID(homepageID string) string {
	id := strings.TrimSpace(homepageID)
	switch {
	case strings.HasPrefix(id, "homepage_sight_"):
		return "sight"
	case strings.HasPrefix(id, "homepage_restaurant_"):
		return "restaurant"
	case strings.HasPrefix(id, "homepage_hotel_"):
		return "hotel"
	case strings.HasPrefix(id, "homepage_vehicle_"):
		return "vehicle"
	case strings.HasPrefix(id, "fixture_homepage_travel_photo_"):
		return "travel_photo"
	case strings.HasPrefix(id, "fixture_homepage_university_"):
		return "university"
	default:
		return ""
	}
}

func normalizeRuntimeEntityRefs(refs []string) []string {
	out := make([]string, 0, len(refs))
	seen := map[string]struct{}{}
	for _, ref := range refs {
		normalized := strings.TrimSpace(ref)
		if normalized == "" {
			continue
		}
		if strings.Contains(normalized, "/") && !strings.HasPrefix(normalized, "entity:") {
			continue
		}
		if _, ok := seen[normalized]; ok {
			continue
		}
		seen[normalized] = struct{}{}
		out = append(out, normalized)
	}
	return out
}

func containsString(items []string, want string) bool {
	for _, item := range items {
		if strings.TrimSpace(item) == want {
			return true
		}
	}
	return false
}

func sameStringSet(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	leftSet := make(map[string]int, len(left))
	for _, item := range left {
		leftSet[strings.TrimSpace(item)]++
	}
	for _, item := range right {
		normalized := strings.TrimSpace(item)
		if leftSet[normalized] == 0 {
			return false
		}
		leftSet[normalized]--
	}
	return true
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
	normalizePostObjectAnchors(post, payload)
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
		hasMarkdown := strings.TrimSpace(post.ArticleMarkdown) != ""
		if !hasMarkdown {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "文章内容不能为空", "article requires articleMarkdown")
		}
		if err := validateArticleMarkdownManifest(post); err != nil {
			return err
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

func validateArticleMarkdownManifest(post *postmodel.Post) error {
	refs := markdownAssetIDs(post.ArticleMarkdown)
	if len(refs) == 0 {
		return nil
	}
	manifestIDs := articleManifestAssetIDs(post.ArticleAssetManifest)
	for _, ref := range refs {
		if !manifestIDs[ref] {
			return rterr.NewInvalidArgument(
				rterr.ModuleContent,
				"文章素材清单缺少引用资源",
				"articleAssetManifest missing asset "+ref,
			)
		}
	}
	return nil
}

func markdownAssetIDs(markdown string) []string {
	uris := markdownAssetURIs(markdown)
	result := []string{}
	for _, uri := range uris {
		result = append(result, strings.TrimPrefix(uri, "asset://"))
	}
	return result
}

func articleManifestAssetIDs(manifest map[string]any) map[string]bool {
	result := map[string]bool{}
	assets, _ := manifest["assets"].([]any)
	for _, item := range assets {
		row, ok := item.(map[string]any)
		if !ok {
			continue
		}
		id := strings.TrimSpace(asString(row["assetId"]))
		if id != "" {
			result[id] = true
		}
	}
	return result
}
