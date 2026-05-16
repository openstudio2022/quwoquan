package recommendation

import "sync/atomic"

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
}

// GlobalEngagementMetrics holds real-time engagement counters.
var GlobalEngagementMetrics EngagementMetrics

// RecordBehaviorMetric updates engagement metrics from a behavior signal.
func RecordBehaviorMetric(signal BehaviorSignal) {
	switch signal.Action {
	case "impression":
		recordImpressionByType(signal.ContentID)
	case "click":
		GlobalEngagementMetrics.ClickTotal.Add(1)
	case "content_depth":
		if signal.EngagementDepth >= 2 {
			recordDeepEngageByType(signal.ContentID)
		}
	case "like":
		GlobalEngagementMetrics.LikeTotal.Add(1)
	case "favorite":
		GlobalEngagementMetrics.FavTotal.Add(1)
	case "share":
		GlobalEngagementMetrics.ShareTotal.Add(1)
	case "comment":
		GlobalEngagementMetrics.CommentTotal.Add(1)
	case "dislike":
		GlobalEngagementMetrics.DislikeTotal.Add(1)
	case "skip":
		GlobalEngagementMetrics.SkipTotal.Add(1)
	}

	recordReferralSource(signal.ReferralSource)

	isSocial := signal.ReferralSource == "friend_share" ||
		signal.ReferralSource == "chat_link" ||
		signal.ReferralSource == "circle_post"
	if isSocial {
		GlobalEngagementMetrics.SocialImpressions.Add(1)
		if signal.Action == "like" || signal.Action == "favorite" ||
			signal.Action == "share" || signal.Action == "comment" ||
			signal.Action == "follow" {
			GlobalEngagementMetrics.SocialPositiveActions.Add(1)
		}
	}
}

func recordImpressionByType(_ string) {
	// In production, lookup content type from cache. For now, increment total.
	GlobalEngagementMetrics.ImpressionPhoto.Add(1)
}

func recordDeepEngageByType(_ string) {
	GlobalEngagementMetrics.DeepEngagePhoto.Add(1)
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
		"click_total":               GlobalEngagementMetrics.ClickTotal.Load(),
		"deep_engage_total":         deepTotal,
		"interaction_total":         interactionTotal,
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
	}
}
