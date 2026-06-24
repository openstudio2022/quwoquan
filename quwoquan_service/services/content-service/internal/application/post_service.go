package application

import (
	"context"
	"fmt"
	"log/slog"
	"net/url"
	rterr "quwoquan_service/runtime/errors"
	runtimemedia "quwoquan_service/runtime/media"
	rtrec "quwoquan_service/runtime/recommendation"
	"quwoquan_service/runtime/repository"
	commentdomain "quwoquan_service/services/content-service/internal/domain/comment"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	postsemantic "quwoquan_service/services/content-service/internal/domain/post/semantic"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
	"strings"
	"sync"
	"time"
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
