package post

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	"strings"
	"time"
)

const appConfigSchema = "app_remote_config"

// AppConfigSlice is the object-local typed response contract for GetAppConfig.
// The service contract remains the wire source of truth; these structs prevent
// the application and HTTP adapter from reintroducing an unbounded map path.
type AppConfigSlice struct {
	Schema           string                    `json:"schema"`
	FetchedAt        time.Time                 `json:"fetchedAt"`
	MaxAgeSec        int64                     `json:"maxAgeSec"`
	ActivationPolicy AppConfigActivationPolicy `json:"activationPolicy"`
	Content          ContentAppConfig          `json:"content"`
	ConfigHash       string                    `json:"configHash"`
}

type AppConfigActivationPolicy struct {
	DefaultActivation string `json:"default"`
	KillSwitches      string `json:"kill_switches"`
}

type ContentAppConfig struct {
	FeatureFlags    ContentAppConfigFeatureFlags     `json:"feature_flags"`
	GrayRelease     ContentAppConfigGrayRelease      `json:"gray_release"`
	ClientStateSync *ContentAppConfigClientStateSync `json:"client_state_sync,omitempty"`
	HomeChannels    []ContentAppConfigHomeChannel    `json:"home_channels,omitempty"`
	Comment         *ContentAppConfigComment         `json:"comment,omitempty"`
	Intersection    *ContentAppConfigIntersection    `json:"intersection,omitempty"`
}

type ContentAppConfigFeatureFlags struct {
	EnableCreateActionEntry             *bool `json:"enable_create_action_entry,omitempty"`
	EnableUnifiedCreateEditor           *bool `json:"enable_unified_create_editor,omitempty"`
	EnableIdentityBasedSurfaces         *bool `json:"enable_identity_based_surfaces,omitempty"`
	EnableIdentityShareTemplate         *bool `json:"enable_identity_share_template,omitempty"`
	EnableArticleDistributionProfiles   *bool `json:"enable_article_distribution_profiles,omitempty"`
	EnableArticleBookReader             *bool `json:"enable_article_book_reader,omitempty"`
	EnableArticlePageCurl               *bool `json:"enable_article_page_curl,omitempty"`
	EnableSharedVideoTimeline           *bool `json:"enable_shared_video_timeline,omitempty"`
	EnableVideoTimelinePreview          *bool `json:"enable_video_timeline_preview,omitempty"`
	EnableHLSCMAFABR                    *bool `json:"enable_hls_cmaf_abr,omitempty"`
	EnableAssistantContentIdentityIndex *bool `json:"enable_assistant_content_identity_index,omitempty"`
	EnableHelperRead                    *bool `json:"enable_helper_read,omitempty"`
	EnableShareToCircle                 *bool `json:"enable_share_to_circle,omitempty"`
	ShowViewCount                       *bool `json:"show_view_count,omitempty"`
}

type ContentAppConfigGrayRelease struct {
	ExperimentBucket string                        `json:"experiment_bucket"`
	CurrentStage     string                        `json:"current_stage"`
	CanaryMatrix     []ContentAppConfigCanaryStage `json:"canary_matrix"`
}

type ContentAppConfigCanaryStage struct {
	Stage          string `json:"stage"`
	RolloutPercent int64  `json:"rolloutPercent"`
}

type ContentAppConfigClientStateSync struct {
	FlushDelaySec           *int64 `json:"flush_delay_sec,omitempty"`
	RetryDelaySec           *int64 `json:"retry_delay_sec,omitempty"`
	MaxBatchSize            *int64 `json:"max_batch_size,omitempty"`
	MaxPendingAgeSec        *int64 `json:"max_pending_age_sec,omitempty"`
	FlushOnForegroundResume *bool  `json:"flush_on_foreground_resume,omitempty"`
	FlushOnNetworkRecovered *bool  `json:"flush_on_network_recovered,omitempty"`
}

type ContentAppConfigHomeChannel struct {
	ID                       string         `json:"id"`
	LabelKey                 *string        `json:"label_key,omitempty"`
	Template                 *string        `json:"template,omitempty"`
	LayoutTemplate           *string        `json:"layout_template,omitempty"`
	PhoneColumns             *int64         `json:"phone_columns,omitempty"`
	SupportsFullSpanModules  *bool          `json:"supports_full_span_modules,omitempty"`
	IntersectionModulePolicy *string        `json:"intersection_module_policy,omitempty"`
	ContentCardPolicy        *string        `json:"content_card_policy,omitempty"`
	FeedQuery                map[string]any `json:"feed_query,omitempty"`
	MoodCopyKey              *string        `json:"mood_copy_key,omitempty"`
	Order                    *int64         `json:"order,omitempty"`
}

type ContentAppConfigComment struct {
	MaxLength                *int64                             `json:"max_length,omitempty"`
	ReplyPreviewCount        *int64                             `json:"reply_preview_count,omitempty"`
	ReplyFirstExpandPageSize *int64                             `json:"reply_first_expand_page_size,omitempty"`
	ReplyExpandPageSize      *int64                             `json:"reply_expand_page_size,omitempty"`
	FoldLineCount            *int64                             `json:"fold_line_count,omitempty"`
	Attachment               *ContentAppConfigCommentAttachment `json:"attachment,omitempty"`
	Enabled                  *bool                              `json:"enabled,omitempty"`
}

type ContentAppConfigCommentAttachment struct {
	MaxImages *int64 `json:"max_images,omitempty"`
}

type ContentAppConfigIntersection struct {
	InlineExpandCount  *int64 `json:"inline_expand_count,omitempty"`
	MaxCandidateWindow *int64 `json:"max_candidate_window,omitempty"`
}

func (s *PostService) GetAppConfig() AppConfigSlice {
	runtimeConfig := normalizeStoryRuntimeConfig(s.storyRuntime)
	canaryMatrix := make([]ContentAppConfigCanaryStage, 0, len(runtimeConfig.CanaryMatrix))
	for _, stage := range runtimeConfig.CanaryMatrix {
		canaryMatrix = append(canaryMatrix, ContentAppConfigCanaryStage{
			Stage:          stage.Stage,
			RolloutPercent: int64(stage.RolloutPercent),
		})
	}
	payload := AppConfigSlice{
		Schema:    appConfigSchema,
		FetchedAt: time.Now().UTC(),
		MaxAgeSec: 21600,
		ActivationPolicy: AppConfigActivationPolicy{
			DefaultActivation: "next_session",
			KillSwitches:      "immediate",
		},
		Content: ContentAppConfig{
			FeatureFlags: contentAppConfigFeatureFlags(runtimeConfig.FeatureFlags),
			GrayRelease: ContentAppConfigGrayRelease{
				ExperimentBucket: runtimeConfig.ExperimentBucket,
				CurrentStage:     runtimeConfig.CurrentStage,
				CanaryMatrix:     canaryMatrix,
			},
		},
	}
	payload.ConfigHash = appConfigHash(payload)
	return payload
}

func contentAppConfigFeatureFlags(flags map[string]bool) ContentAppConfigFeatureFlags {
	return ContentAppConfigFeatureFlags{
		EnableCreateActionEntry:             boolValue(flags, "enable_create_action_entry"),
		EnableUnifiedCreateEditor:           boolValue(flags, "enable_unified_create_editor"),
		EnableIdentityBasedSurfaces:         boolValue(flags, "enable_identity_based_surfaces"),
		EnableIdentityShareTemplate:         boolValue(flags, "enable_identity_share_template"),
		EnableArticleDistributionProfiles:   boolValue(flags, "enable_article_distribution_profiles"),
		EnableArticleBookReader:             boolValue(flags, "enable_article_book_reader"),
		EnableArticlePageCurl:               boolValue(flags, "enable_article_page_curl"),
		EnableSharedVideoTimeline:           boolValue(flags, "enable_shared_video_timeline"),
		EnableVideoTimelinePreview:          boolValue(flags, "enable_video_timeline_preview"),
		EnableHLSCMAFABR:                    boolValue(flags, "enable_hls_cmaf_abr"),
		EnableAssistantContentIdentityIndex: boolValue(flags, "enable_assistant_content_identity_index"),
		EnableHelperRead:                    boolValue(flags, "enable_helper_read"),
		EnableShareToCircle:                 boolValue(flags, "enable_share_to_circle"),
		ShowViewCount:                       boolValue(flags, "show_view_count"),
	}
}

func boolValue(values map[string]bool, key string) *bool {
	value, exists := values[key]
	if !exists {
		return nil
	}
	return &value
}

func appConfigHash(payload AppConfigSlice) string {
	encoded, _ := json.Marshal(payload)
	canonical := map[string]any{}
	_ = json.Unmarshal(encoded, &canonical)
	delete(canonical, "configHash")
	delete(canonical, "fetchedAt")
	data, _ := json.Marshal(canonical)
	sum := sha256.Sum256(data)
	return "sha256:" + hex.EncodeToString(sum[:])
}

type PostCounterSlice struct {
	LikeCount    int64 `json:"likeCount"`
	CommentCount int64 `json:"commentCount"`
	ShareCount   int64 `json:"shareCount"`
}

func (s *PostService) GetCounters(ctx context.Context, postID string) (PostCounterSlice, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return PostCounterSlice{}, contentgenerated.AppErrorFromPostNotFound("post not found")
	}
	// 评论数取 DB 权威 count（含二级、排除软删），与 ListComments.totalCount 同源；
	// post.CommentCount 仅作 feed/详情页去规范化加速器。读路径机会式自愈：发现加速器
	// 与权威 count 漂移时按权威值单 $set 收敛（无整文档改写），保证最终一致。
	if s.commentCounts == nil {
		return PostCounterSlice{}, contentgenerated.AppErrorFromRequiredDependencyUnavailable("Comment CountReader is required")
	}
	commentCount := post.CommentCount
	if n, err := s.commentCounts.CountByPost(ctx, post.ID); err == nil {
		commentCount = n
		if n != post.CommentCount {
			if _, serr := s.store.SetCommentCount(ctx, post.ID, n); serr != nil {
				s.logger.Warn("GetCounters: self-heal comment count failed", "postId", post.ID, "error", serr.Error())
			}
		}
	} else {
		s.logger.Warn("GetCounters: authoritative comment count failed", "postId", post.ID, "error", err.Error())
	}
	return PostCounterSlice{
		LikeCount:    post.LikeCount,
		CommentCount: commentCount,
		ShareCount:   post.ShareCount,
	}, nil
}
