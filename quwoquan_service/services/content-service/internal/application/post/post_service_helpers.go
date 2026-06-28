package post

import (
	"net/url"
	rterr "quwoquan_service/runtime/errors"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"sort"
	"strconv"
	"strings"
	"time"
)

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
		"thumbnailUrl":       post.ThumbnailUrl,
		"videoUrl":           post.VideoUrl,
		"coverStrategy":      post.CoverStrategy,
		"coverFrameTimeMs":   post.CoverFrameTimeMs,
		"durationMs":         durationMsFromPost(post),
		"width":              widthFromPost(post),
		"height":             heightFromPost(post),
		"mediaItems":         post.MediaItems,
		"semanticMentions":   post.SemanticMentions,
		"tagRefs":            asStringSlice(post.TagRefs),
		"entityRefs":         asStringSlice(post.EntityRefs),
		"primaryHomepageId":  strings.TrimSpace(post.PrimaryHomepageId),
		"canonicalEntityId":  strings.TrimSpace(post.CanonicalEntityId),
	}
}

func durationMsFromPost(post *postmodel.Post) int64 {
	if post == nil {
		return 0
	}
	if duration := int64FromMaps("durationMs", post.DeviceInfo, post.ArticleRenderProfile, post.PrimaryHomepageSnapshot); duration > 0 {
		return duration
	}
	return 0
}

func widthFromPost(post *postmodel.Post) int64 {
	if post == nil {
		return 0
	}
	return int64FromMaps("width", post.DeviceInfo, post.ArticleRenderProfile, post.PrimaryHomepageSnapshot)
}

func heightFromPost(post *postmodel.Post) int64 {
	if post == nil {
		return 0
	}
	return int64FromMaps("height", post.DeviceInfo, post.ArticleRenderProfile, post.PrimaryHomepageSnapshot)
}

func int64FromMaps(key string, sources ...map[string]any) int64 {
	for _, source := range sources {
		if len(source) == 0 {
			continue
		}
		if value := asInt64Flexible(source[key]); value > 0 {
			return value
		}
	}
	return 0
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

func normalizeVideoCoverContract(post *postmodel.Post) {
	if post == nil || strings.TrimSpace(post.ContentType) != "video" {
		return
	}
	post.VideoUrl = strings.TrimSpace(post.VideoUrl)
	post.ThumbnailUrl = strings.TrimSpace(post.ThumbnailUrl)
	post.CoverUrl = strings.TrimSpace(post.CoverUrl)
	post.CoverStrategy = normalizeCoverStrategy(post.CoverStrategy)
	if post.CoverFrameTimeMs < 0 {
		post.CoverFrameTimeMs = 0
	}
	if post.ThumbnailUrl == "" && post.CoverUrl != "" {
		post.ThumbnailUrl = post.CoverUrl
	}
	if post.CoverUrl == "" && post.ThumbnailUrl != "" {
		post.CoverUrl = post.ThumbnailUrl
	}
	if post.ThumbnailUrl == "" && post.VideoUrl != "" {
		post.ThumbnailUrl = deriveVideoThumbnailURL(post.VideoUrl, post.CoverFrameTimeMs)
	}
	if post.CoverUrl == "" && post.ThumbnailUrl != "" {
		post.CoverUrl = post.ThumbnailUrl
	}
}

func normalizeCoverStrategy(strategy string) string {
	switch strings.TrimSpace(strategy) {
	case "manual":
		return "manual"
	default:
		return "first_frame"
	}
}

func deriveVideoThumbnailURL(videoURL string, frameTimeMs int64) string {
	trimmed := strings.TrimSpace(videoURL)
	if trimmed == "" {
		return ""
	}
	parsed, err := url.Parse(trimmed)
	if err != nil {
		if strings.Contains(trimmed, "?") {
			return trimmed + "&variant=thumb"
		}
		return trimmed + "?variant=thumb"
	}
	query := parsed.Query()
	if query.Get("variant") == "" {
		query.Set("variant", "thumb")
	}
	if frameTimeMs > 0 {
		query.Set("t", strconv.FormatInt(frameTimeMs, 10))
	}
	parsed.RawQuery = query.Encode()
	return parsed.String()
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
		if strings.TrimSpace(post.ThumbnailUrl) == "" && strings.TrimSpace(post.CoverUrl) == "" {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "视频封面不能为空", "video requires thumbnailUrl or coverUrl")
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
