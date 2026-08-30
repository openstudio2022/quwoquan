package feed

import (
	"context"
	"fmt"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	rtrec "quwoquan_service/runtime/recommendation"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

type videoAdaptiveDelivery struct {
	MediaAssetID             string
	MediaAssetVersion        int64
	HLSCMAFMasterManifestURL string
	HLSCMAFDescriptorVersion int64
}

func firstVideoAdaptiveDelivery(items []postports.PostMediaItemSlice) videoAdaptiveDelivery {
	for _, item := range items {
		if !strings.EqualFold(strings.TrimSpace(item.Kind), "video") {
			continue
		}
		assetID := strings.TrimSpace(item.MediaAssetID)
		if assetID == "" || item.MediaAssetVersion <= 0 {
			return videoAdaptiveDelivery{}
		}
		delivery := videoAdaptiveDelivery{
			MediaAssetID:      assetID,
			MediaAssetVersion: item.MediaAssetVersion,
		}
		manifest := strings.TrimSpace(item.HLSCMAFMasterManifestURL)
		if manifest != "" && item.HLSCMAFDescriptorVersion > 0 {
			delivery.HLSCMAFMasterManifestURL = manifest
			delivery.HLSCMAFDescriptorVersion = item.HLSCMAFDescriptorVersion
		}
		return delivery
	}
	return videoAdaptiveDelivery{}
}

func canonicalReleasePostDelivered(
	post *postports.PostFeedItemSlice,
	activeReleaseID string,
	activeManifestDigest string,
	requirePlayableVideo bool,
) bool {
	if post == nil || strings.TrimSpace(activeReleaseID) == "" ||
		strings.TrimSpace(activeManifestDigest) == "" {
		return false
	}
	if strings.TrimSpace(post.SourceOwner) != "qwq_data" ||
		strings.TrimSpace(post.ReleaseID) != strings.TrimSpace(activeReleaseID) ||
		strings.TrimSpace(post.ManifestDigest) != strings.TrimSpace(activeManifestDigest) ||
		strings.TrimSpace(post.LifecycleStatus) != "active" {
		return false
	}
	if !requirePlayableVideo {
		return true
	}
	return strings.EqualFold(strings.TrimSpace(string(post.ContentType)), "video") &&
		strings.TrimSpace(post.VideoURL) != "" &&
		post.DurationMS > 0
}

func releaseBoundHydrationMatches(
	post *postports.PostFeedItemSlice,
	item *rtrec.FeedItem,
	activeReleaseID string,
	activeManifestDigest string,
) bool {
	activeReleaseID = strings.TrimSpace(activeReleaseID)
	activeManifestDigest = strings.TrimSpace(activeManifestDigest)
	if post == nil || item == nil || activeReleaseID == "" || activeManifestDigest == "" {
		return post != nil && item != nil
	}
	candidateCanonical := strings.TrimSpace(item.SourceOwner) == "qwq_data" ||
		strings.EqualFold(strings.TrimSpace(item.SupplySource), "data_engineering")
	postCanonical := strings.TrimSpace(post.SourceOwner) == "qwq_data"
	if !candidateCanonical && !postCanonical {
		return true
	}
	return candidateCanonical && postCanonical &&
		strings.TrimSpace(item.ReleaseID) == activeReleaseID &&
		strings.TrimSpace(item.ManifestDigest) == activeManifestDigest &&
		strings.TrimSpace(item.LifecycleStatus) == "active" &&
		strings.TrimSpace(post.ReleaseID) == activeReleaseID &&
		strings.TrimSpace(post.ManifestDigest) == activeManifestDigest &&
		strings.TrimSpace(post.LifecycleStatus) == "active"
}

func (s *FeedService) resolveViewerBlockedPersonaIDs(
	ctx context.Context,
	viewerPersonaID string,
) ([]string, error) {
	viewerPersonaID = strings.TrimSpace(viewerPersonaID)
	if viewerPersonaID == "" {
		return nil, nil
	}
	if s == nil || s.viewerBlocks == nil {
		return nil, fmt.Errorf("feed viewer block reader is not configured")
	}
	blocked, err := s.viewerBlocks.ListBlockedPersonaIDs(ctx, viewerPersonaID)
	if err != nil {
		return nil, fmt.Errorf("read feed viewer block facts: %w", err)
	}
	return blocked, nil
}

func requiredDependencyFailure(stage rtrec.FailureStage, cause error) *rterr.AppError {
	typed := rtrec.NewFeedFailure(stage, cause)
	return contentgenerated.AppErrorFromRequiredDependencyUnavailable(typed.Error()).
		WithContextAttributes(rterr.RuntimeErrorContextAttribute{
			Key:   "failureStage",
			Value: string(stage),
		})
}

func storageReadFailure(operation string, cause error) *rterr.AppError {
	message := strings.TrimSpace(operation)
	if cause != nil {
		message = fmt.Sprintf("%s: %v", message, cause)
	}
	return contentgenerated.AppErrorFromStorageReadFailed(message)
}

func normalizeFeedSort(sortValue string) string {
	switch strings.TrimSpace(strings.ToLower(sortValue)) {
	case "", rtrec.FeedSortRecommend:
		return rtrec.FeedSortRecommend
	default:
		return rtrec.FeedSortRecommend
	}
}

func mapContentTypeToViewType(contentType string) string {
	switch strings.TrimSpace(contentType) {
	case "micro":
		return "moment"
	case "image":
		return "image"
	case "video":
		return "video"
	case "article":
		return "article"
	default:
		return "image"
	}
}

func normalizeRequestType(t string) string {
	switch strings.TrimSpace(strings.ToLower(t)) {
	case "", "recommended", "following", "travel", "travel_photography", "premium", "similar", "featured", "immersive", "精品", "旅行", "旅游":
		return ""
	case "photo":
		return "image"
	case "note":
		return "article"
	default:
		return strings.TrimSpace(strings.ToLower(t))
	}
}

type feedRoute struct {
	FeedType  rtrec.FeedType
	Surface   string
	Vertical  string
	ChannelID string
}

func resolveFeedRoute(req ListFeedRequest) feedRoute {
	// 首页频道路由（B1/B16 收口）：channelId 是频道推荐主链路的唯一路由标识，
	// 优先于 type/subCategory token。following 走关注召回主路（fail-closed），
	// travel 归入 travel_photography 垂类，其余频道进推荐引擎并按 channelId 归因。
	if channel := strings.TrimSpace(strings.ToLower(req.ChannelID)); channel != "" {
		switch channel {
		case "following":
			return feedRoute{
				FeedType:  rtrec.FeedFollow,
				Surface:   "home",
				ChannelID: "following",
			}
		case "travel", "travel_photography":
			return feedRoute{
				FeedType:  rtrec.FeedDiscovery,
				Surface:   "travel_photography",
				Vertical:  "travel_photography",
				ChannelID: "travel_photography",
			}
		case "premium", "premium_stream":
			return feedRoute{
				FeedType:  rtrec.FeedSimilar,
				Surface:   "premium_stream",
				ChannelID: "premium_stream",
			}
		default:
			// recommend/campus/photography/tech/car 及运营远程新增频道：
			// 统一进推荐引擎，channelId 原样归因（交集池与埋点按频道区分）。
			return feedRoute{
				FeedType:  rtrec.FeedDiscovery,
				Surface:   "home",
				ChannelID: channel,
			}
		}
	}
	tokens := []string{
		strings.TrimSpace(strings.ToLower(req.Type)),
		strings.TrimSpace(strings.ToLower(req.SubCategory)),
	}
	for _, token := range tokens {
		switch token {
		case "premium", "similar", "featured", "immersive", "精品", "quality":
			return feedRoute{
				FeedType:  rtrec.FeedSimilar,
				Surface:   "premium_stream",
				ChannelID: "premium_stream",
			}
		case "travel", "travel_photography", "旅行", "旅游":
			return feedRoute{
				FeedType:  rtrec.FeedDiscovery,
				Surface:   "travel_photography",
				Vertical:  "travel_photography",
				ChannelID: "travel_photography",
			}
		}
	}
	return feedRoute{
		FeedType:  rtrec.FeedDiscovery,
		Surface:   "home",
		ChannelID: "discovery",
	}
}

func feedItemAttribution(post *postports.PostFeedItemSlice, item *rtrec.FeedItem) (float64, string, string, string) {
	if item != nil {
		return item.QualityScore,
			strings.TrimSpace(item.RecallPath),
			firstNonEmptyLocal(item.ContentVertical, postContentVertical(post)),
			firstNonEmptyLocal(item.SupplySource, postSupplySource(post))
	}
	return 0,
		"post_query",
		postContentVertical(post),
		postSupplySource(post)
}

func firstNonEmptyLocal(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

func postContentVertical(post *postports.PostFeedItemSlice) string {
	if post == nil {
		return "general"
	}
	if vertical := strings.TrimSpace(strings.ToLower(post.ContentVertical)); vertical != "" {
		return vertical
	}
	if postMatchesVertical(post, "travel_photography") {
		return "travel_photography"
	}
	return "general"
}

func postSupplySource(post *postports.PostFeedItemSlice) string {
	if post == nil {
		return "unknown"
	}
	if strings.TrimSpace(post.SourceOwner) == "qwq_data" {
		return "data_engineering"
	}
	return "ugc"
}

func postMatchesVertical(post *postports.PostFeedItemSlice, vertical string) bool {
	vertical = strings.TrimSpace(strings.ToLower(vertical))
	if vertical == "" {
		return true
	}
	if strings.TrimSpace(strings.ToLower(post.ContentVertical)) == vertical {
		return true
	}
	haystack := strings.ToLower(strings.Join(postVerticalTokens(post), " "))
	switch vertical {
	case "travel_photography":
		return strings.Contains(haystack, "travel") ||
			strings.Contains(haystack, "旅行") ||
			strings.Contains(haystack, "旅游") ||
			strings.Contains(haystack, "景区") ||
			strings.Contains(haystack, "路线") ||
			strings.Contains(haystack, "自驾")
	default:
		return false
	}
}

func postVerticalTokens(post *postports.PostFeedItemSlice) []string {
	tokens := []string{string(post.ContentType)}
	tokens = append(tokens, post.TagRefs...)
	tokens = append(tokens, post.EntityRefs...)
	return tokens
}

func normalizeRequestedIdentity(identity string) string {
	switch strings.TrimSpace(strings.ToLower(identity)) {
	case "moment", "work":
		return strings.TrimSpace(strings.ToLower(identity))
	default:
		return ""
	}
}

func ResolvedContentIdentity(contentType, contentIdentity string) string {
	normalized := strings.TrimSpace(strings.ToLower(contentIdentity))
	if normalized == "moment" || normalized == "work" {
		return normalized
	}
	if strings.TrimSpace(strings.ToLower(contentType)) == "micro" {
		return "moment"
	}
	return "work"
}

func toLowerSet(items []string) map[string]struct{} {
	out := make(map[string]struct{}, len(items))
	for _, item := range items {
		v := strings.ToLower(strings.TrimSpace(item))
		if v != "" {
			out[v] = struct{}{}
		}
	}
	return out
}

func containsBlockedKeyword(post *postports.PostFeedItemSlice, blocked map[string]struct{}) bool {
	if len(blocked) == 0 {
		return false
	}
	targets := []string{
		post.Title,
		post.Body,
	}
	if len(post.TagRefs) > 0 {
		targets = append(targets, post.TagRefs...)
	}
	for _, text := range targets {
		normalized := strings.ToLower(strings.TrimSpace(text))
		if normalized == "" {
			continue
		}
		for keyword := range blocked {
			if strings.Contains(normalized, keyword) {
				return true
			}
		}
	}
	return false
}
