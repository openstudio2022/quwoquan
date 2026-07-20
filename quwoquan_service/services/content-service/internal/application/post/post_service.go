package post

import (
	"log/slog"
	rterr "quwoquan_service/runtime/errors"
	messaging "quwoquan_service/runtime/messaging"
	rtrec "quwoquan_service/runtime/recommendation"
	commentports "quwoquan_service/services/content-service/internal/domain/comment/ports"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
	postsemantic "quwoquan_service/services/content-service/internal/domain/post/semantic"
	"strings"
	"sync"
)

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
	store                 postDataAccess
	mediaAssetBindings    MediaAssetBindingReader
	signaler              rtrec.SignalProcessor
	publisher             messaging.EventPublisher
	logger                *slog.Logger
	mu                    sync.RWMutex
	tombstoneReader       postports.TombstoneReader
	commentCounts         commentports.CountReader
	publicationRateGate   postports.PublicationRateGate
	publicationSafetyGate postports.PublicationSafetyGate
	storyRuntime          StoryRuntimeConfig
}

func NewPostService(dataPorts DataPorts, opts ...PostServiceOption) *PostService {
	if dataPorts.Aggregate == nil || dataPorts.Detail == nil ||
		dataPorts.Collection == nil || dataPorts.Counters == nil {
		panic("PostService requires aggregate, detail, collection and counter data ports")
	}
	s := &PostService{
		store:        postDataAccess{ports: dataPorts},
		logger:       slog.Default(),
		storyRuntime: defaultStoryRuntimeConfig(),
	}
	s.mediaAssetBindings = dataPorts.MediaAssets
	// 与 Aggregate/Detail 同一 adapter 通常同时实现持久墓碑读端口。
	if reader, ok := dataPorts.Aggregate.(postports.TombstoneReader); ok {
		s.tombstoneReader = reader
	}
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

// WithEventPublisher enables domain event publishing (e.g. PostPublished).
func WithEventPublisher(pub messaging.EventPublisher) PostServiceOption {
	return func(s *PostService) { s.publisher = pub }
}

// WithCommentReaders 注入 Post 计数所需的 Comment 具名只读端口。
// Comment 写模型和命令 Facade 不得回流到 PostService。
func WithCommentReaders(readers interface {
	commentports.CountReader
}) PostServiceOption {
	return func(s *PostService) {
		if readers != nil {
			s.commentCounts = readers
		}
	}
}

func WithPublicationAdmission(
	rateGate postports.PublicationRateGate,
	safetyGate postports.PublicationSafetyGate,
) PostServiceOption {
	return func(s *PostService) {
		s.publicationRateGate = rateGate
		s.publicationSafetyGate = safetyGate
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

func normalizePostForRead(post *postmodel.Post) *postmodel.Post {
	if post == nil {
		return nil
	}
	copy := *post
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
