package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log/slog"
	"math"
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
	commentdomain "quwoquan_service/services/content-service/internal/domain/comment"
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
	store         persistence.PostRepository
	signaler      rtrec.SignalProcessor
	publisher     repository.EventPublisher
	projector     Projector
	logger        *slog.Logger
	mu            sync.RWMutex
	reactions     map[string]map[string]contentReactionState // postID -> userID -> state
	distributions map[string]map[string]bool                 // postID -> circleID -> active
	reshares      map[string]map[string]bool                 // postID -> (circleID:userID) -> active
	tombstones    map[string]time.Time                       // postID -> deletedAt
	mediaAssets   map[string]postmodel.MediaAsset            // mediaID -> asset
	uploadSession map[string]string                          // sessionID -> mediaID
	// 评论读写已迁出进程内存：commentStore 承载评论 CRUD/分页/排序/计数（Mongo+Redis
	// 或内存降级），commentReactionStore 承载三态反应权威成员关系（R-CMT01）。
	commentStore         commentdomain.Store
	commentReactionStore commentdomain.ReactionStore
	commentMaxLen        int // configurable, default 500
	storyRuntime         StoryRuntimeConfig
	mediaCDNBase         string
	mediaUploadBase      string
	mediaStore           runtimemedia.MediaStore
	ipResolver           IPLocationResolver // 评论属地解析（默认确定性 stub，生产注入 GeoIP）
}

func NewPostService(store persistence.PostRepository, opts ...PostServiceOption) *PostService {
	s := &PostService{
		store:           store,
		logger:          slog.Default(),
		reactions:       map[string]map[string]contentReactionState{},
		distributions:   map[string]map[string]bool{},
		reshares:        map[string]map[string]bool{},
		tombstones:      map[string]time.Time{},
		mediaAssets:     map[string]postmodel.MediaAsset{},
		uploadSession:   map[string]string{},
		commentMaxLen:   500,
		storyRuntime:    defaultStoryRuntimeConfig(),
		mediaCDNBase:    "https://media.quwoquan.invalid",
		mediaUploadBase: "https://media-origin.quwoquan.invalid",
		mediaStore:      runtimemedia.NewMockMediaStore(),
		ipResolver:      newDeterministicProvinceResolver(),
	}
	for _, opt := range opts {
		opt(s)
	}
	// 未注入持久化实现时（alpha/单元测试）默认内存降级实现；语义与 Mongo 完全一致。
	if s.commentStore == nil {
		s.commentStore = persistence.NewMemoryCommentStore()
	}
	if s.commentReactionStore == nil {
		s.commentReactionStore = persistence.NewMemoryCommentReactionStore()
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

// WithCommentStore injects the comment repository (Mongo+Redis in beta/gamma/prod,
// in-memory in alpha/tests). Interface lives in the domain layer (R01/R10).
func WithCommentStore(store commentdomain.Store) PostServiceOption {
	return func(s *PostService) {
		if store != nil {
			s.commentStore = store
		}
	}
}

// WithCommentReactionStore injects the authoritative three-state comment reaction
// store. Membership is authoritative; per-comment counts are derived from it.
func WithCommentReactionStore(store commentdomain.ReactionStore) PostServiceOption {
	return func(s *PostService) {
		if store != nil {
			s.commentReactionStore = store
		}
	}
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

func (s *PostService) BindMediaAssetsToComment(ctx context.Context, commentID, userID string, assetIDs []string) (map[string]any, error) {
	commentID = strings.TrimSpace(commentID)
	if commentID == "" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "commentId 不能为空", "missing commentId")
	}
	userID = strings.TrimSpace(userID)

	comment, found := s.commentStore.FindByID(ctx, commentID)
	if !found || strings.TrimSpace(comment.Status) == "deleted" {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "comment_not_found"),
			"评论不存在",
			"comment not found",
		)
	}
	authorID := strings.TrimSpace(comment.AuthorId)
	if userID != "" && authorID != "" && authorID != userID {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "comment_forbidden_update"),
			"无权更新此评论附件",
			"comment author mismatch",
		)
	}
	boundIDs, attachments, err := s.prepareCommentAttachments(comment.PostId, authorID, assetIDs)
	if err != nil {
		return nil, err
	}
	if _, err := s.commentStore.SetAttachments(ctx, commentID, boundIDs, attachments); err != nil {
		return nil, rterr.NewUnavailable(
			rterr.ModuleContent, "附件绑定失败，请稍后重试", "comment set attachments failed: "+err.Error(),
		)
	}
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
	viewerID string,
	direction string,
	limit int,
) ([]postmodel.ProfileInteractionActivityView, error) {
	profileSubjectID = strings.TrimSpace(profileSubjectID)
	viewerID = strings.TrimSpace(viewerID)
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
	if limit > profileInteractionActivityMaxLimit {
		limit = profileInteractionActivityMaxLimit
	}

	// 点赞/转发仍为进程内互动：读锁内只做轻量快照（不触达外部 store、不构造投影）。
	refs := s.snapshotProfileInteractionRefs(profileSubjectID, direction)
	// 评论互动已迁出内存：经 commentStore 持久化读取（Mongo+Redis 或内存降级）。
	commentRefs, err := s.gatherCommentInteractionRefs(ctx, profileSubjectID, direction)
	if err != nil {
		return nil, err
	}
	refs = append(refs, commentRefs...)

	// viewer 对互动评论的真实三态反应：一次性批量解析（避免 N+1）。
	commentIDs := make([]string, 0, len(commentRefs))
	for _, ref := range commentRefs {
		if ref.commentModel != nil {
			commentIDs = append(commentIDs, ref.commentModel.ID)
		}
	}
	viewerReactions := map[string]commentdomain.Reaction{}
	if viewerID != "" && len(commentIDs) > 0 {
		if m, rerr := s.commentReactionStore.ReactionsForUser(ctx, viewerID, commentIDs); rerr == nil {
			viewerReactions = m
		} else {
			s.logger.Warn("ListProfileInteractionActivities: viewer reactions failed", "error", rerr.Error())
		}
	}

	// 按 postID 去重 hydrate（每条作品仅取一次），再投影 / 归属过滤 / 排序 / 截断。
	postCache := make(map[string]*postmodel.Post, len(refs))
	items := make([]postmodel.ProfileInteractionActivityView, 0, len(refs))
	for _, ref := range refs {
		post, cached := postCache[ref.postID]
		if !cached {
			post, _ = s.store.FindByID(ctx, ref.postID)
			postCache[ref.postID] = post
		}
		if post == nil {
			continue
		}
		if direction == "received" && post.AuthorId != profileSubjectID {
			continue
		}
		createdAt := post.UpdatedAt
		viewerReaction := ""
		if ref.activityType == "comment" && ref.commentModel != nil {
			createdAt = ref.commentModel.CreatedAt
			viewerReaction = string(viewerReactions[ref.commentModel.ID])
		}
		items = append(items, buildProfileInteractionActivityView(profileInteractionProjectionInput{
			ActivityID:         ref.activityID,
			ActivityType:       ref.activityType,
			Direction:          direction,
			ActorID:            ref.actorID,
			TargetSubAccountID: post.AuthorId,
			Post:               post,
			Comment:            ref.commentModel,
			ViewerReaction:     viewerReaction,
			CreatedAt:          createdAt,
		}))
	}

	sort.Slice(items, func(i, j int) bool {
		return items[i].CreatedAt.After(items[j].CreatedAt)
	})
	if len(items) > limit {
		items = items[:limit]
	}
	return items, nil
}

// profileInteractionActivityMaxLimit clamp 上界：杜绝调用方传入超大 limit 触发无界结果集。
const profileInteractionActivityMaxLimit = 50

// profileInteractionRef 是轻量互动引用；不携带作品/投影，hydrate 推迟到后续阶段。
// 评论互动携带强类型评论模型（R04），点赞/转发互动不携带评论。
type profileInteractionRef struct {
	activityID   string
	activityType string
	actorID      string
	postID       string
	commentModel *postmodel.Comment
}

// gatherCommentInteractionRefs 经 commentStore 收集匹配方向的评论互动引用：
// sent = 主页主体发表的评论；received = 他人对主页主体作品发表的评论。
// 评论权威存储已迁出进程内存（R-CMT01），此处读取持久化层而非内存快照。
func (s *PostService) gatherCommentInteractionRefs(
	ctx context.Context,
	profileSubjectID string,
	direction string,
) ([]profileInteractionRef, error) {
	var comments []postmodel.Comment
	if direction == "sent" {
		page, err := s.commentStore.ListByAuthor(ctx, profileSubjectID, "", profileInteractionActivityMaxLimit)
		if err != nil {
			return nil, rterr.NewUnavailable(
				rterr.ModuleContent, "互动加载失败，请稍后重试", "gather sent comment interactions failed: "+err.Error(),
			)
		}
		comments = page.Comments
	} else {
		authored := s.store.ListByAuthor(ctx, profileSubjectID, 10000, "")
		postIDs := make([]string, 0, len(authored))
		for _, p := range authored {
			postIDs = append(postIDs, p.ID)
		}
		if len(postIDs) == 0 {
			return nil, nil
		}
		page, err := s.commentStore.ListReceivedByPostAuthor(ctx, profileSubjectID, postIDs, "", profileInteractionActivityMaxLimit)
		if err != nil {
			return nil, rterr.NewUnavailable(
				rterr.ModuleContent, "互动加载失败，请稍后重试", "gather received comment interactions failed: "+err.Error(),
			)
		}
		comments = page.Comments
	}
	refs := make([]profileInteractionRef, 0, len(comments))
	for i := range comments {
		c := comments[i]
		actorID := strings.TrimSpace(c.AuthorId)
		if !profileInteractionActorMatches(direction, actorID, profileSubjectID) {
			continue
		}
		model := c
		refs = append(refs, profileInteractionRef{
			activityID:   fmt.Sprintf("comment:%s", c.ID),
			activityType: "comment",
			actorID:      actorID,
			postID:       strings.TrimSpace(c.PostId),
			commentModel: &model,
		})
	}
	return refs, nil
}

// snapshotProfileInteractionRefs 在读锁内收集匹配方向/主页主体的点赞/转发互动引用。
// 仅做内存遍历与方向侧（actor）过滤，不调用外部 post store；received 的作者归属在锁外
// hydrate 后再校验。评论互动改由 gatherCommentInteractionRefs 经持久化层收集。
func (s *PostService) snapshotProfileInteractionRefs(
	profileSubjectID string,
	direction string,
) []profileInteractionRef {
	s.mu.RLock()
	defer s.mu.RUnlock()

	refs := make([]profileInteractionRef, 0)

	for postID, byUser := range s.reactions {
		pid := strings.TrimSpace(postID)
		for actorID, state := range byUser {
			if !state.Liked {
				continue
			}
			if !profileInteractionActorMatches(direction, actorID, profileSubjectID) {
				continue
			}
			refs = append(refs, profileInteractionRef{
				activityID:   fmt.Sprintf("like:%s:%s", pid, actorID),
				activityType: "like",
				actorID:      actorID,
				postID:       pid,
			})
		}
	}

	for postID, shares := range s.reshares {
		pid := strings.TrimSpace(postID)
		for shareKey, active := range shares {
			if !active {
				continue
			}
			actorID := shareActorID(shareKey)
			if actorID == "" {
				continue
			}
			if !profileInteractionActorMatches(direction, actorID, profileSubjectID) {
				continue
			}
			refs = append(refs, profileInteractionRef{
				activityID:   fmt.Sprintf("share:%s:%s", pid, actorID),
				activityType: "share",
				actorID:      actorID,
				postID:       pid,
			})
		}
	}

	return refs
}

// profileInteractionActorMatches 仅做方向侧（actor）匹配：sent 要求 actor 即主页主体；
// received 要求 actor 非主页主体（作者归属在锁外 hydrate 后再校验）。
func profileInteractionActorMatches(direction, actorID, profileSubjectID string) bool {
	actorID = strings.TrimSpace(actorID)
	if direction == "sent" {
		return actorID == profileSubjectID
	}
	return actorID != profileSubjectID
}

func shareActorID(shareKey string) string {
	parts := strings.Split(strings.TrimSpace(shareKey), ":")
	if len(parts) == 0 {
		return ""
	}
	return strings.TrimSpace(parts[len(parts)-1])
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
	now := time.Now().UTC()
	if replyToCommentID != "" {
		target, found := s.commentStore.FindByID(ctx, replyToCommentID)
		if !found {
			return nil, 0, rterr.NewAppError(
				rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "comment_not_found"),
				"回复目标不存在",
				"reply target comment not found",
			)
		}
		replyToUserId = strings.TrimSpace(target.AuthorId)
		parentCommentID = strings.TrimSpace(target.ParentCommentId)
		if parentCommentID == "" {
			parentCommentID = replyToCommentID
		}
		// 回复数变化影响父评论综合分：原子 +1 并落写时确定性快照分。
		if parent, pok := s.commentStore.FindByID(ctx, parentCommentID); pok {
			projectedParent := *parent
			projectedParent.ReplyCount = parent.ReplyCount + 1
			newScore := commentRecommendedScoreModel(projectedParent, now)
			if _, _, err := s.commentStore.AdjustReplyCount(ctx, parentCommentID, 1, newScore); err != nil {
				s.logger.Warn("AddComment: adjust parent reply count failed", "error", err.Error())
			}
		}
	}

	// 媒体附件绑定仍依赖进程内存的 mediaAssets，单独短临界区加锁。
	attachmentIDs, attachments, err := s.prepareCommentAttachments(post.ID, authorID, attachmentMediaIDs)
	if err != nil {
		return nil, 0, err
	}
	normalizedMentions := normalizeCommentMentions(mentions)
	assistantMentioned := commentHasAssistantMention(normalizedMentions)

	// 评论属地：创建时按受信客户端 IP 解析省级展示串并落库快照；
	// 解析不出则留空（前端不展示），绝不臆造属地。
	ipLocation := ""
	if s.ipResolver != nil {
		ipLocation = strings.TrimSpace(s.ipResolver.Resolve(clientIPFromContext(ctx)))
	}
	comment := postmodel.Comment{
		ID:                    fmt.Sprintf("comment_%d", now.UnixNano()),
		PostId:                post.ID,
		AuthorId:              authorID,
		PersonaContextVersion: asInt64Flexible(personaContextVersion),
		Content:               content,
		IpLocation:            ipLocation,
		ReplyToCommentId:      replyToCommentID,
		ReplyToUserId:         replyToUserId,
		ParentCommentId:       parentCommentID,
		AttachmentMediaIds:    attachmentIDs,
		Attachments:           attachments,
		Mentions:              normalizedMentions,
		AssistantMentioned:    assistantMentioned,
		ReplyCount:            0,
		LikeCount:             0,
		DislikeCount:          0,
		ViewerReaction:        "none",
		RecommendedScore:      0,
		Status:                "visible",
		CanDelete:             true,
		CanReply:              true,
		CanReport:             false,
		CreatedAt:             now,
	}
	// 综合分写时确定性预计算并落字段：排序只读快照值，消除读路径 time.Since 漂移。
	comment.RecommendedScore = commentRecommendedScoreModel(comment, now)
	if err := s.commentStore.Create(ctx, &comment); err != nil {
		return nil, 0, rterr.NewUnavailable(
			rterr.ModuleContent,
			"评论保存失败，请稍后重试",
			"comment persist failed: "+err.Error(),
		)
	}

	// 计数热路径：单字段原子 $inc(+1)，消除每次增删的全量 CountDocuments + 整文档
	// 改写热写。单一真相源仍是评论集 DB count；Post.commentCount 仅为去规范化加速
	// 器，GetCounters 读路径按权威 count 机会式自愈漂移。$inc 失败才回退权威对账。
	commentCount, ok, err := s.store.AdjustCommentCount(ctx, post.ID, 1)
	if err != nil || !ok {
		if err != nil {
			s.logger.Warn("AddComment: adjust comment count failed", "postId", post.ID, "error", err.Error())
		}
		commentCount = s.reconcilePostCommentCount(ctx, post.ID)
	}
	projectedComment := s.projectCommentSingle(ctx, comment, authorID, true)

	if s.publisher != nil {
		featurePayload := commentFeaturePayload(*post, content, parentCommentID, replyToUserId, attachments)
		_ = s.publisher.Publish(ctx, repository.DomainEvent{
			Type:          "CommentCreated",
			AggregateType: "Post",
			AggregateID:   post.ID,
			Payload: map[string]any{
				"commentId":             comment.ID,
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

	return projectedComment, commentCount, nil
}

// prepareCommentAttachments locks the in-memory media asset table only for the
// duration of attachment binding (asset table is the last in-process state).
func (s *PostService) prepareCommentAttachments(postID, authorID string, assetIDs []string) ([]string, []map[string]any, error) {
	if len(assetIDs) == 0 {
		return []string{}, []map[string]any{}, nil
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.prepareCommentAttachmentsLocked(postID, authorID, assetIDs)
}

// reconcilePostCommentCount recomputes the authoritative non-deleted comment
// count (top-level + replies) from the comment store and converges the
// denormalized Post.commentCount accelerator to it via a single atomic $set
// (no full-document rewrite). The comment-collection count is the single source
// of truth; this is the self-heal / error-fallback path, NOT the hot write path
// (Add/Delete use atomic $inc — see AddComment/DeleteComment).
func (s *PostService) reconcilePostCommentCount(ctx context.Context, postID string) int64 {
	n, err := s.commentStore.CountByPost(ctx, postID)
	if err != nil {
		s.logger.Warn("reconcile comment count failed", "postId", postID, "error", err.Error())
		if post, ok := s.store.FindByID(ctx, postID); ok {
			return post.CommentCount
		}
		return 0
	}
	if _, err := s.store.SetCommentCount(ctx, postID, n); err != nil {
		s.logger.Warn("reconcile set comment count failed", "postId", postID, "error", err.Error())
	}
	return n
}

func (s *PostService) ListComments(ctx context.Context, postID, viewerID, cursor, sort string, limit int) ([]map[string]any, string, int, error) {
	if limit <= 0 {
		limit = 20
	}
	postID = strings.TrimSpace(postID)
	mode := commentdomain.NormalizeSortMode(sort)
	page, err := s.commentStore.ListTopLevel(ctx, postID, mode, strings.TrimSpace(cursor), limit)
	if err != nil {
		return nil, "", 0, rterr.NewUnavailable(
			rterr.ModuleContent, "评论加载失败，请稍后重试", "list comments failed: "+err.Error(),
		)
	}
	// totalCount 单一真相源：DB 权威 count（含二级、排除软删），与切换排序无关。
	totalCount, err := s.commentStore.CountByPost(ctx, postID)
	if err != nil {
		s.logger.Warn("ListComments: count failed", "postId", postID, "error", err.Error())
	}
	projected := s.projectCommentPage(ctx, postID, page.Comments, viewerID, true)
	return projected, page.NextCursor, int(totalCount), nil
}

func (s *PostService) ListCommentReplies(ctx context.Context, postID, commentID, viewerID, cursor string, limit int) ([]map[string]any, string, int, error) {
	if limit <= 0 {
		limit = 10
	}
	postID = strings.TrimSpace(postID)
	parentID := strings.TrimSpace(commentID)
	parent, found := s.commentStore.FindByID(ctx, parentID)
	if !found || strings.TrimSpace(parent.PostId) != postID || strings.TrimSpace(parent.Status) == "deleted" {
		return nil, "", 0, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "comment_not_found"),
			"评论不存在",
			"parent comment not found",
		)
	}
	page, err := s.commentStore.ListReplies(ctx, postID, parentID, strings.TrimSpace(cursor), limit)
	if err != nil {
		return nil, "", 0, rterr.NewUnavailable(
			rterr.ModuleContent, "回复加载失败，请稍后重试", "list replies failed: "+err.Error(),
		)
	}
	// 该父评论下全部非删除回复数，作为渐进分页「展开 N 条回复」的权威总数。
	totalCount, err := s.commentStore.CountReplies(ctx, postID, parentID)
	if err != nil {
		s.logger.Warn("ListCommentReplies: count failed", "parentId", parentID, "error", err.Error())
	}
	projected := s.projectCommentPage(ctx, postID, page.Comments, viewerID, false)
	return projected, page.NextCursor, int(totalCount), nil
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

// wilsonLowerBound 返回赞占比的 Wilson 95% 置信下界（positive/total），
// 低样本时收敛保守，避免「1 赞 0 踩」直接压过「99 赞 1 踩」。
func wilsonLowerBound(positive, total int64) float64 {
	if total <= 0 || positive < 0 {
		return 0
	}
	n := float64(total)
	phat := float64(positive) / n
	const z = 1.96
	denom := 1 + z*z/n
	centre := phat + z*z/(2*n)
	margin := z * math.Sqrt((phat*(1-phat)+z*z/(4*n))/n)
	lower := (centre - margin) / denom
	if lower < 0 {
		return 0
	}
	return lower
}

func maxInt64(a, b int64) int64 {
	if a > b {
		return a
	}
	return b
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

func (s *PostService) DeleteComment(ctx context.Context, postID, commentID, userID string) error {
	postID = strings.TrimSpace(postID)
	commentID = strings.TrimSpace(commentID)
	userID = strings.TrimSpace(userID)

	existing, found := s.commentStore.FindByID(ctx, commentID)
	if !found || strings.TrimSpace(existing.PostId) != postID || strings.TrimSpace(existing.Status) == "deleted" {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"评论不存在",
			"comment not found",
		)
	}
	if author := strings.TrimSpace(existing.AuthorId); userID != "" && author != "" && author != userID {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "comment_forbidden_delete"),
			"无权删除此评论",
			"comment author mismatch",
		)
	}

	_, removed, err := s.commentStore.SoftDelete(ctx, commentID, time.Now().UTC())
	if err != nil {
		return rterr.NewUnavailable(
			rterr.ModuleContent, "评论删除失败，请稍后重试", "comment soft delete failed: "+err.Error(),
		)
	}
	if !removed {
		// 并发下另一删除已抢先落地（SoftDelete 仅对未删文档生效）：幂等返回，
		// 不重复递减计数、不重复回收父 replyCount，避免双重扣减。
		return nil
	}
	// 删除回复时回收父评论 replyCount 并重算父评论快照分。
	if parentID := commentParentOfModel(*existing); parentID != "" {
		if parent, pok := s.commentStore.FindByID(ctx, parentID); pok {
			projectedParent := *parent
			if projectedParent.ReplyCount > 0 {
				projectedParent.ReplyCount--
			}
			newScore := commentRecommendedScoreModel(projectedParent, time.Now().UTC())
			if _, _, err := s.commentStore.AdjustReplyCount(ctx, parentID, -1, newScore); err != nil {
				s.logger.Warn("DeleteComment: adjust parent reply count failed", "error", err.Error())
			}
		}
	}
	// 软删评论的全部三态反应一并清理（计数派生自成员关系，避免残留）。
	if err := s.commentReactionStore.PurgeComment(ctx, commentID); err != nil {
		s.logger.Warn("DeleteComment: purge reactions failed", "error", err.Error())
	}
	// 计数热路径：单字段原子 $inc(-1)。单一真相源仍是评论集 DB count，$inc 失败
	// 才回退权威对账自愈。
	if _, _, err := s.store.AdjustCommentCount(ctx, postID, -1); err != nil {
		s.logger.Warn("DeleteComment: adjust comment count failed", "postId", postID, "error", err.Error())
		s.reconcilePostCommentCount(ctx, postID)
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

// SetCommentPinned 由内容作者置顶/取消置顶一级评论。仅内容作者可操作，
// 二级回复不可置顶。置顶时写入 isPinned/pinnedAt，取消时清空。
func (s *PostService) SetCommentPinned(ctx context.Context, postID, commentID, userID string, pinned bool) (map[string]any, error) {
	postID = strings.TrimSpace(postID)
	commentID = strings.TrimSpace(commentID)
	userID = strings.TrimSpace(userID)

	post, ok := s.store.FindByID(ctx, postID)
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	if userID == "" || strings.TrimSpace(post.AuthorId) != userID {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "comment_pin_forbidden"),
			"仅内容作者可置顶评论",
			"only post author can pin comments",
		)
	}

	target, found := s.commentStore.FindByID(ctx, commentID)
	if !found || strings.TrimSpace(target.PostId) != postID || strings.TrimSpace(target.Status) == "deleted" {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "comment_not_found"),
			"评论不存在",
			"comment not found",
		)
	}
	if !commentTopLevelModel(*target) {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "comment_pin_invalid_target"),
			"只能置顶一级评论",
			"only top-level comments can be pinned",
		)
	}

	if _, err := s.commentStore.SetPinned(ctx, commentID, pinned, time.Now().UTC()); err != nil {
		return nil, rterr.NewUnavailable(
			rterr.ModuleContent, "置顶操作失败，请稍后重试", "comment set pinned failed: "+err.Error(),
		)
	}
	refreshed, _ := s.commentStore.FindByID(ctx, commentID)
	if refreshed == nil {
		refreshed = target
	}
	projected := s.projectCommentSingle(ctx, *refreshed, userID, true)

	if s.publisher != nil {
		action := "unpin"
		if pinned {
			action = "pin"
		}
		_ = s.publisher.Publish(ctx, repository.DomainEvent{
			Type:          "CommentPinChanged",
			AggregateType: "Post",
			AggregateID:   postID,
			Payload: map[string]any{
				"commentId":   commentID,
				"postId":      postID,
				"operatorId":  userID,
				"auditAction": action,
				"auditedAt":   time.Now().UTC().Format(time.RFC3339),
			},
			OccurredAt: time.Now().UTC().Format(time.RFC3339),
		})
	}
	return projected, nil
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

	existing, found := s.commentStore.FindByID(ctx, commentID)
	if !found || strings.TrimSpace(existing.Status) == "deleted" {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "comment_not_found"),
			"评论不存在",
			"comment not found",
		)
	}
	postID := strings.TrimSpace(existing.PostId)
	authorID := strings.TrimSpace(existing.AuthorId)

	desired, _ := commentdomain.NormalizeReaction(reaction)
	// 三态反应权威成员关系落库（Mongo comment_reactions），幂等。
	if err := s.commentReactionStore.Set(ctx, commentID, userID, desired); err != nil {
		return nil, rterr.NewUnavailable(
			rterr.ModuleContent, "操作失败，请稍后重试", "comment reaction set failed: "+err.Error(),
		)
	}
	// 计数直接派生自权威成员关系（Mongo 索引 Count，并发下精确），落库的
	// likeCount/recommendedScore 永不陈旧；不再经只写不读的 Redis 计数器回填。
	likeCount, dislikeCount, err := s.commentReactionStore.Counts(ctx, commentID)
	if err != nil {
		s.logger.Warn("ReactToComment: counts failed", "commentId", commentID, "error", err.Error())
		likeCount, dislikeCount = existing.LikeCount, existing.DislikeCount
	}
	now := time.Now().UTC()
	scored := *existing
	scored.LikeCount = likeCount
	scored.DislikeCount = dislikeCount
	newScore := commentRecommendedScoreModel(scored, now)
	if _, err := s.commentStore.SetReactionState(ctx, commentID, likeCount, dislikeCount, newScore); err != nil {
		return nil, rterr.NewUnavailable(
			rterr.ModuleContent, "操作失败，请稍后重试", "comment reaction state failed: "+err.Error(),
		)
	}
	scored.RecommendedScore = newScore
	updated := s.projectCommentSingle(ctx, scored, userID, false)

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

func (s *PostService) ListCommentsByAuthor(ctx context.Context, userID, cursor string, limit int) ([]map[string]any, string, error) {
	if limit <= 0 {
		limit = 20
	}
	userID = strings.TrimSpace(userID)
	page, err := s.commentStore.ListByAuthor(ctx, userID, strings.TrimSpace(cursor), limit)
	if err != nil {
		return nil, "", rterr.NewUnavailable(
			rterr.ModuleContent, "评论加载失败，请稍后重试", "list comments by author failed: "+err.Error(),
		)
	}
	projected := s.projectCommentsAcrossPosts(ctx, page.Comments, userID)
	return projected, page.NextCursor, nil
}

func (s *PostService) ListCommentsForPostAuthor(ctx context.Context, userID, cursor string, limit int) ([]map[string]any, string, error) {
	if limit <= 0 {
		limit = 20
	}
	userID = strings.TrimSpace(userID)

	authored := s.store.ListByAuthor(ctx, userID, 10000, "")
	postIDs := make([]string, 0, len(authored))
	for _, p := range authored {
		postIDs = append(postIDs, p.ID)
	}
	page, err := s.commentStore.ListReceivedByPostAuthor(ctx, userID, postIDs, strings.TrimSpace(cursor), limit)
	if err != nil {
		return nil, "", rterr.NewUnavailable(
			rterr.ModuleContent, "评论加载失败，请稍后重试", "list received comments failed: "+err.Error(),
		)
	}
	projected := s.projectCommentsAcrossPosts(ctx, page.Comments, userID)
	return projected, page.NextCursor, nil
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
			// 评论客户端配置真相源：contracts/metadata/content/post/projections/
			// content_app_config_client.yaml#comment_defaults（端 CommentRemoteConfig 消费）。
			"comment": map[string]any{
				"max_length":                   s.commentMaxLen,
				"reply_preview_count":          1,
				"reply_first_expand_page_size": 5,
				"reply_expand_page_size":       10,
				"fold_line_count":              3,
				"attachment":                   map[string]any{"max_images": 1},
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
	// 评论数取 DB 权威 count（含二级、排除软删），与 ListComments.totalCount 同源；
	// post.CommentCount 仅作 feed/详情页去规范化加速器。读路径机会式自愈：发现加速器
	// 与权威 count 漂移时按权威值单 $set 收敛（无整文档改写），保证最终一致。
	commentCount := post.CommentCount
	if n, err := s.commentStore.CountByPost(ctx, post.ID); err == nil {
		commentCount = n
		if n != post.CommentCount {
			if _, serr := s.store.SetCommentCount(ctx, post.ID, n); serr != nil {
				s.logger.Warn("GetCounters: self-heal comment count failed", "postId", post.ID, "error", serr.Error())
			}
		}
	} else {
		s.logger.Warn("GetCounters: authoritative comment count failed", "postId", post.ID, "error", err.Error())
	}
	return map[string]any{
		"like":    post.LikeCount,
		"comment": commentCount,
		"share":   post.ShareCount,
	}, nil
}

// GetCommentCountsDelta returns an explainable incremental comment-count report
// for a post relative to a client baseline `since`. It answers "since you last
// synced, N comments were created and M were removed; the authoritative total is
// now T". The interval is half-open (since, watermark]: createdSinceCount counts
// comments whose createdAt falls in the window (regardless of later deletion),
// deletedSinceCount counts comments soft-deleted (status=deleted) whose deletedAt
// falls in the window, and currentTotal is the authoritative non-deleted count.
// watermark is a monotonic UTC timestamp the client passes as the next `since`,
// so consecutive deltas never double-count nor skip an event. A zero `since`
// (first sync) is treated as unbounded-below to seed the baseline.
func (s *PostService) GetCommentCountsDelta(ctx context.Context, postID string, since time.Time) (map[string]any, error) {
	postID = strings.TrimSpace(postID)
	if _, ok := s.store.FindByID(ctx, postID); !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	// 水位线取本次查询时刻；下次以此为 since，半开区间 (since, watermark] 保证
	// 相邻两次 delta 既不重复也不遗漏。
	watermark := time.Now().UTC()
	since = since.UTC()
	created, err := s.commentStore.CountCreatedBetween(ctx, postID, since, watermark)
	if err != nil {
		return nil, rterr.NewUnavailable(
			rterr.ModuleContent, "评论计数加载失败，请稍后重试", "count created between failed: "+err.Error(),
		)
	}
	deleted, err := s.commentStore.CountDeletedBetween(ctx, postID, since, watermark)
	if err != nil {
		return nil, rterr.NewUnavailable(
			rterr.ModuleContent, "评论计数加载失败，请稍后重试", "count deleted between failed: "+err.Error(),
		)
	}
	currentTotal, err := s.commentStore.CountByPost(ctx, postID)
	if err != nil {
		return nil, rterr.NewUnavailable(
			rterr.ModuleContent, "评论计数加载失败，请稍后重试", "current total count failed: "+err.Error(),
		)
	}
	sinceWire := ""
	if !since.IsZero() {
		sinceWire = since.Format(time.RFC3339Nano)
	}
	return map[string]any{
		"createdSinceCount": created,
		"deletedSinceCount": deleted,
		"currentTotal":      currentTotal,
		"watermark":         watermark.Format(time.RFC3339Nano),
		"since":             sinceWire,
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

func asBoolFlexible(v any) bool {
	switch vv := v.(type) {
	case bool:
		return vv
	case string:
		return strings.EqualFold(strings.TrimSpace(vv), "true")
	}
	return false
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
