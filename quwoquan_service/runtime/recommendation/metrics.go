package recommendation

import (
	"strings"
	"sync/atomic"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// Prometheus counters that mirror the atomic EngagementMetrics, enabling
// Grafana dashboards and alerting without polling the JSON snapshot endpoint.
var (
	engImpressionTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "rec",
		Subsystem: "engagement",
		Name:      "impression_total",
		Help:      "Content impressions by type.",
	}, []string{"content_type"})

	engClickTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "rec",
		Subsystem: "engagement",
		Name:      "click_total",
		Help:      "Content clicks by type.",
	}, []string{"content_type"})

	engDeepEngageTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "rec",
		Subsystem: "engagement",
		Name:      "deep_engage_total",
		Help:      "Deep engagements (depth >= L2) by type.",
	}, []string{"content_type"})

	engInteractionTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "rec",
		Subsystem: "engagement",
		Name:      "interaction_total",
		Help:      "User interactions by action.",
	}, []string{"action"})

	engReferralTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "rec",
		Subsystem: "engagement",
		Name:      "referral_total",
		Help:      "Events by referral source.",
	}, []string{"source"})

	engSocialConversionTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "rec",
		Subsystem: "engagement",
		Name:      "social_conversion_total",
		Help:      "Social source positive conversions by action.",
	}, []string{"action"})

	engNegativeFeedbackTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "rec",
		Subsystem: "engagement",
		Name:      "negative_feedback_total",
		Help:      "Negative feedback by action.",
	}, []string{"action"})
)

// EngagementMetrics tracks business-level recommendation quality metrics.
// Thread-safe via atomic operations. Periodically snapshot for reporting.
type EngagementMetrics struct {
	// Impressions by content type
	ImpressionPhoto   atomic.Int64
	ImpressionVideo   atomic.Int64
	ImpressionArticle atomic.Int64
	ImpressionMoment  atomic.Int64

	// Clicks (CTR numerator)
	ClickTotal atomic.Int64

	// Deep engagement (depth >= L2)
	DeepEngagePhoto   atomic.Int64
	DeepEngageVideo   atomic.Int64
	DeepEngageArticle atomic.Int64
	DeepEngageMoment  atomic.Int64

	// Interactions
	LikeTotal    atomic.Int64
	FavTotal     atomic.Int64
	ShareTotal   atomic.Int64
	CommentTotal atomic.Int64

	// Per-type click/like/share breakdown
	ClickPhoto   atomic.Int64
	ClickVideo   atomic.Int64
	ClickArticle atomic.Int64
	ClickMoment  atomic.Int64
	LikePhoto    atomic.Int64
	LikeVideo    atomic.Int64
	LikeArticle  atomic.Int64
	LikeMoment   atomic.Int64
	SharePhoto   atomic.Int64
	ShareVideo   atomic.Int64
	ShareArticle atomic.Int64
	ShareMoment  atomic.Int64
	FavPhoto     atomic.Int64
	FavVideo     atomic.Int64
	FavArticle   atomic.Int64
	FavMoment    atomic.Int64
	CommentPhoto   atomic.Int64
	CommentVideo   atomic.Int64
	CommentArticle atomic.Int64
	CommentMoment  atomic.Int64

	// Negative feedback
	DislikeTotal atomic.Int64
	SkipTotal    atomic.Int64

	// Social source conversions
	SocialImpressions      atomic.Int64
	SocialPositiveActions   atomic.Int64

	// Referral source distribution
	SourceOrganicFeed      atomic.Int64
	SourceFriendShare      atomic.Int64
	SourceChatLink         atomic.Int64
	SourceCirclePost       atomic.Int64
	SourceAuthorProfile    atomic.Int64
	SourceEntityPage       atomic.Int64
	SourceSearch           atomic.Int64
	SourcePushNotification atomic.Int64

	// Model vs Rule bucket counters (pipeline level)
	ModelHits        atomic.Int64
	RuleHits         atomic.Int64
	ModelTimeouts    atomic.Int64
	TotalRequests    atomic.Int64
	EmptyFeedResults atomic.Int64
}

// GlobalEngagementMetrics holds real-time engagement counters.
var GlobalEngagementMetrics EngagementMetrics

// resolveContentType returns the content type from the signal, falling back
// to tag inference for backward compatibility with events lacking ContentType.
func resolveContentType(signal BehaviorSignal) string {
	if signal.ContentType != "" {
		return strings.ToLower(signal.ContentType)
	}
	return inferContentTypeFromTags(signal.Tags)
}

// RecordBehaviorMetric updates engagement metrics from a behavior signal.
// Both atomic counters (for JSON snapshot) and Prometheus counters are updated.
func RecordBehaviorMetric(signal BehaviorSignal) {
	ct := resolveContentType(signal)
	if ct == "" {
		ct = "unknown"
	}

	switch signal.Action {
	case "impression":
		recordImpressionByType(signal.Tags)
		engImpressionTotal.WithLabelValues(ct).Inc()
	case "click":
		GlobalEngagementMetrics.ClickTotal.Add(1)
		recordClickByType(signal.Tags)
		engClickTotal.WithLabelValues(ct).Inc()
		engInteractionTotal.WithLabelValues("click").Inc()
	case "content_depth":
		if signal.EngagementDepth >= 2 {
			recordDeepEngageByType(signal.Tags)
			engDeepEngageTotal.WithLabelValues(ct).Inc()
		}
	case "like":
		GlobalEngagementMetrics.LikeTotal.Add(1)
		recordLikeByType(signal.Tags)
		engInteractionTotal.WithLabelValues("like").Inc()
	case "favorite":
		GlobalEngagementMetrics.FavTotal.Add(1)
		recordFavoriteByType(signal.Tags)
		engInteractionTotal.WithLabelValues("favorite").Inc()
	case "share":
		GlobalEngagementMetrics.ShareTotal.Add(1)
		recordShareByType(signal.Tags)
		engInteractionTotal.WithLabelValues("share").Inc()
	case "comment":
		GlobalEngagementMetrics.CommentTotal.Add(1)
		recordCommentByType(signal.Tags)
		engInteractionTotal.WithLabelValues("comment").Inc()
	case "dislike":
		GlobalEngagementMetrics.DislikeTotal.Add(1)
		engNegativeFeedbackTotal.WithLabelValues("dislike").Inc()
	case "skip":
		GlobalEngagementMetrics.SkipTotal.Add(1)
		engNegativeFeedbackTotal.WithLabelValues("skip").Inc()
	case "follow":
		engInteractionTotal.WithLabelValues("follow").Inc()
	}

	if signal.ReferralSource != "" {
		recordReferralSource(signal.ReferralSource)
		engReferralTotal.WithLabelValues(signal.ReferralSource).Inc()
	}

	isSocial := signal.ReferralSource == "friend_share" ||
		signal.ReferralSource == "chat_link" ||
		signal.ReferralSource == "circle_post"
	if isSocial {
		GlobalEngagementMetrics.SocialImpressions.Add(1)
		if signal.Action == "like" || signal.Action == "favorite" ||
			signal.Action == "share" || signal.Action == "comment" ||
			signal.Action == "follow" {
			GlobalEngagementMetrics.SocialPositiveActions.Add(1)
			engSocialConversionTotal.WithLabelValues(signal.Action).Inc()
		}
	}
}

func inferContentTypeFromTags(tags []string) string {
	for _, t := range tags {
		dim := ClassifyTagDimension(t)
		if dim == DimensionFormat {
			parts := strings.SplitN(t, "/", 3)
			if len(parts) >= 2 {
				switch strings.ToLower(parts[1]) {
				case "photo", "图片":
					return "photo"
				case "video", "视频":
					return "video"
				case "article", "文章":
					return "article"
				case "moment", "点滴":
					return "moment"
				}
			}
		}
	}
	return ""
}

func recordImpressionByType(tags []string) {
	switch inferContentTypeFromTags(tags) {
	case "video":
		GlobalEngagementMetrics.ImpressionVideo.Add(1)
	case "article":
		GlobalEngagementMetrics.ImpressionArticle.Add(1)
	case "moment":
		GlobalEngagementMetrics.ImpressionMoment.Add(1)
	default:
		GlobalEngagementMetrics.ImpressionPhoto.Add(1)
	}
}

func recordDeepEngageByType(tags []string) {
	switch inferContentTypeFromTags(tags) {
	case "video":
		GlobalEngagementMetrics.DeepEngageVideo.Add(1)
	case "article":
		GlobalEngagementMetrics.DeepEngageArticle.Add(1)
	case "moment":
		GlobalEngagementMetrics.DeepEngageMoment.Add(1)
	default:
		GlobalEngagementMetrics.DeepEngagePhoto.Add(1)
	}
}

func recordClickByType(tags []string) {
	switch inferContentTypeFromTags(tags) {
	case "video":
		GlobalEngagementMetrics.ClickVideo.Add(1)
	case "article":
		GlobalEngagementMetrics.ClickArticle.Add(1)
	case "moment":
		GlobalEngagementMetrics.ClickMoment.Add(1)
	default:
		GlobalEngagementMetrics.ClickPhoto.Add(1)
	}
}

func recordLikeByType(tags []string) {
	switch inferContentTypeFromTags(tags) {
	case "video":
		GlobalEngagementMetrics.LikeVideo.Add(1)
	case "article":
		GlobalEngagementMetrics.LikeArticle.Add(1)
	case "moment":
		GlobalEngagementMetrics.LikeMoment.Add(1)
	default:
		GlobalEngagementMetrics.LikePhoto.Add(1)
	}
}

func recordShareByType(tags []string) {
	switch inferContentTypeFromTags(tags) {
	case "video":
		GlobalEngagementMetrics.ShareVideo.Add(1)
	case "article":
		GlobalEngagementMetrics.ShareArticle.Add(1)
	case "moment":
		GlobalEngagementMetrics.ShareMoment.Add(1)
	default:
		GlobalEngagementMetrics.SharePhoto.Add(1)
	}
}

func recordFavoriteByType(tags []string) {
	switch inferContentTypeFromTags(tags) {
	case "video":
		GlobalEngagementMetrics.FavVideo.Add(1)
	case "article":
		GlobalEngagementMetrics.FavArticle.Add(1)
	case "moment":
		GlobalEngagementMetrics.FavMoment.Add(1)
	default:
		GlobalEngagementMetrics.FavPhoto.Add(1)
	}
}

func recordCommentByType(tags []string) {
	switch inferContentTypeFromTags(tags) {
	case "video":
		GlobalEngagementMetrics.CommentVideo.Add(1)
	case "article":
		GlobalEngagementMetrics.CommentArticle.Add(1)
	case "moment":
		GlobalEngagementMetrics.CommentMoment.Add(1)
	default:
		GlobalEngagementMetrics.CommentPhoto.Add(1)
	}
}

func recordReferralSource(source string) {
	switch source {
	case "organic_feed":
		GlobalEngagementMetrics.SourceOrganicFeed.Add(1)
	case "friend_share":
		GlobalEngagementMetrics.SourceFriendShare.Add(1)
	case "chat_link":
		GlobalEngagementMetrics.SourceChatLink.Add(1)
	case "circle_post":
		GlobalEngagementMetrics.SourceCirclePost.Add(1)
	case "author_profile":
		GlobalEngagementMetrics.SourceAuthorProfile.Add(1)
	case "entity_page":
		GlobalEngagementMetrics.SourceEntityPage.Add(1)
	case "search":
		GlobalEngagementMetrics.SourceSearch.Add(1)
	case "push_notification":
		GlobalEngagementMetrics.SourcePushNotification.Add(1)
	}
}

// RecordPipelineResult updates model vs rule bucket counters from a pipeline result.
func RecordPipelineResult(modelUsed string, isEmpty bool) {
	GlobalEngagementMetrics.TotalRequests.Add(1)
	switch modelUsed {
	case "rule", "":
		GlobalEngagementMetrics.RuleHits.Add(1)
	default:
		GlobalEngagementMetrics.ModelHits.Add(1)
	}
	if isEmpty {
		GlobalEngagementMetrics.EmptyFeedResults.Add(1)
	}
}

// RecordModelTimeoutMetric increments the model timeout counter.
func RecordModelTimeoutMetric() {
	GlobalEngagementMetrics.ModelTimeouts.Add(1)
}

// SnapshotEngagementMetrics returns a point-in-time business metrics map.
func SnapshotEngagementMetrics() map[string]int64 {
	impressionTotal := GlobalEngagementMetrics.ImpressionPhoto.Load() +
		GlobalEngagementMetrics.ImpressionVideo.Load() +
		GlobalEngagementMetrics.ImpressionArticle.Load() +
		GlobalEngagementMetrics.ImpressionMoment.Load()

	deepTotal := GlobalEngagementMetrics.DeepEngagePhoto.Load() +
		GlobalEngagementMetrics.DeepEngageVideo.Load() +
		GlobalEngagementMetrics.DeepEngageArticle.Load() +
		GlobalEngagementMetrics.DeepEngageMoment.Load()

	interactionTotal := GlobalEngagementMetrics.LikeTotal.Load() +
		GlobalEngagementMetrics.FavTotal.Load() +
		GlobalEngagementMetrics.ShareTotal.Load() +
		GlobalEngagementMetrics.CommentTotal.Load()

	return map[string]int64{
		"impression_total":          impressionTotal,
		"impression_photo":          GlobalEngagementMetrics.ImpressionPhoto.Load(),
		"impression_video":          GlobalEngagementMetrics.ImpressionVideo.Load(),
		"impression_article":        GlobalEngagementMetrics.ImpressionArticle.Load(),
		"impression_moment":         GlobalEngagementMetrics.ImpressionMoment.Load(),
		"click_total":               GlobalEngagementMetrics.ClickTotal.Load(),
		"click_photo":               GlobalEngagementMetrics.ClickPhoto.Load(),
		"click_video":               GlobalEngagementMetrics.ClickVideo.Load(),
		"click_article":             GlobalEngagementMetrics.ClickArticle.Load(),
		"click_moment":              GlobalEngagementMetrics.ClickMoment.Load(),
		"deep_engage_total":         deepTotal,
		"deep_engage_photo":         GlobalEngagementMetrics.DeepEngagePhoto.Load(),
		"deep_engage_video":         GlobalEngagementMetrics.DeepEngageVideo.Load(),
		"deep_engage_article":       GlobalEngagementMetrics.DeepEngageArticle.Load(),
		"deep_engage_moment":        GlobalEngagementMetrics.DeepEngageMoment.Load(),
		"interaction_total":         interactionTotal,
		"like_photo":                GlobalEngagementMetrics.LikePhoto.Load(),
		"like_video":                GlobalEngagementMetrics.LikeVideo.Load(),
		"like_article":              GlobalEngagementMetrics.LikeArticle.Load(),
		"like_moment":               GlobalEngagementMetrics.LikeMoment.Load(),
		"share_photo":               GlobalEngagementMetrics.SharePhoto.Load(),
		"share_video":               GlobalEngagementMetrics.ShareVideo.Load(),
		"share_article":             GlobalEngagementMetrics.ShareArticle.Load(),
		"share_moment":              GlobalEngagementMetrics.ShareMoment.Load(),
		"fav_photo":                 GlobalEngagementMetrics.FavPhoto.Load(),
		"fav_video":                 GlobalEngagementMetrics.FavVideo.Load(),
		"fav_article":               GlobalEngagementMetrics.FavArticle.Load(),
		"fav_moment":                GlobalEngagementMetrics.FavMoment.Load(),
		"comment_photo":             GlobalEngagementMetrics.CommentPhoto.Load(),
		"comment_video":             GlobalEngagementMetrics.CommentVideo.Load(),
		"comment_article":           GlobalEngagementMetrics.CommentArticle.Load(),
		"comment_moment":            GlobalEngagementMetrics.CommentMoment.Load(),
		"dislike_total":             GlobalEngagementMetrics.DislikeTotal.Load(),
		"skip_total":                GlobalEngagementMetrics.SkipTotal.Load(),
		"social_impressions":        GlobalEngagementMetrics.SocialImpressions.Load(),
		"social_positive_actions":   GlobalEngagementMetrics.SocialPositiveActions.Load(),
		"source_organic_feed":       GlobalEngagementMetrics.SourceOrganicFeed.Load(),
		"source_friend_share":       GlobalEngagementMetrics.SourceFriendShare.Load(),
		"source_chat_link":          GlobalEngagementMetrics.SourceChatLink.Load(),
		"source_circle_post":        GlobalEngagementMetrics.SourceCirclePost.Load(),
		"source_author_profile":     GlobalEngagementMetrics.SourceAuthorProfile.Load(),
		"source_entity_page":        GlobalEngagementMetrics.SourceEntityPage.Load(),
		"source_search":             GlobalEngagementMetrics.SourceSearch.Load(),
		"source_push_notification":  GlobalEngagementMetrics.SourcePushNotification.Load(),
		"model_hits":                GlobalEngagementMetrics.ModelHits.Load(),
		"rule_hits":                 GlobalEngagementMetrics.RuleHits.Load(),
		"model_timeouts":            GlobalEngagementMetrics.ModelTimeouts.Load(),
		"total_requests":            GlobalEngagementMetrics.TotalRequests.Load(),
		"empty_feed_results":        GlobalEngagementMetrics.EmptyFeedResults.Load(),
	}
}
