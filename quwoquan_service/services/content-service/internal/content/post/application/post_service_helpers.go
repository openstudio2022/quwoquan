package post

import (
	"net/url"
	rterr "quwoquan_service/runtime/errors"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
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

func projectionPayloadForPost(post *postmodel.Post) map[string]any {
	if post == nil {
		return nil
	}
	return map[string]any{
		"postId":                    post.ID,
		"publishIntentId":           post.PublishIntentId,
		"localDraftId":              post.LocalDraftId,
		"authorId":                  post.AuthorId,
		"authorDisplayNameSnapshot": post.AuthorDisplayNameSnapshot,
		"authorAvatarUrlSnapshot":   post.AuthorAvatarUrlSnapshot,
		"contentType":               post.ContentType,
		"contentIdentity":           post.ContentIdentity,
		"status":                    post.Status,
		"visibility":                normalizeVisibility(post.Visibility),
		"moderationStatus":          strings.ToLower(strings.TrimSpace(post.ModerationStatus)),
		"contentDigest":             strings.TrimSpace(post.ContentDigest),
		"assistantUsePolicy":        post.AssistantUsePolicy,
		"publishedAt":               formatTimePtr(post.PublishedAt),
		"createdAt":                 formatTimePtr(post.CreatedAt),
		"updatedAt":                 formatTimePtr(post.UpdatedAt),
		"title":                     post.Title,
		"body":                      post.Body,
		"summary":                   post.Summary,
		"mediaUrls":                 post.MediaUrls,
		"coverUrl":                  post.CoverUrl,
		"thumbnailUrl":              post.ThumbnailUrl,
		"videoUrl":                  post.VideoUrl,
		"coverStrategy":             post.CoverStrategy,
		"coverFrameTimeMs":          post.CoverFrameTimeMs,
		"durationMs":                durationMsFromPost(post),
		"width":                     widthFromPost(post),
		"height":                    heightFromPost(post),
		"likeCount":                 post.LikeCount,
		"commentCount":              post.CommentCount,
		"shareCount":                post.ShareCount,
		"contentVertical":           post.ContentVertical,
		"mediaItems":                post.MediaItems,
		"semanticMentions":          post.SemanticMentions,
		"tagRefs":                   asStringSlice(post.TagRefs),
		"entityRefs":                asStringSlice(post.EntityRefs),
		"primaryHomepageId":         strings.TrimSpace(post.PrimaryHomepageId),
		"primaryHomepageSnapshot":   postHomepageSnapshotForEvent(post),
		"visitedAt":                 formatTimePtr(post.VisitedAt),
		"captureDisclosure":         asStringSlice(post.CaptureDisclosure),
	}
}

func postHomepageSnapshotForEvent(post *postmodel.Post) any {
	if post == nil || strings.TrimSpace(post.PrimaryHomepageId) == "" {
		return nil
	}
	return map[string]any{
		"canonicalEntityId": strings.TrimSpace(post.PrimaryHomepageSnapshot.CanonicalEntityId),
		"title":             strings.TrimSpace(post.PrimaryHomepageSnapshot.Title),
		"subtitle":          strings.TrimSpace(post.PrimaryHomepageSnapshot.Subtitle),
		"coverUrl":          strings.TrimSpace(post.PrimaryHomepageSnapshot.CoverUrl),
	}
}

func durationMsFromPost(post *postmodel.Post) int64 {
	if post == nil {
		return 0
	}
	if post.DurationMs > 0 {
		return post.DurationMs
	}
	for _, duration := range []int64{
		post.DeviceInfo.DurationMs,
		post.ArticleRenderProfile.DurationMs,
		post.PrimaryHomepageSnapshot.DurationMs,
	} {
		if duration > 0 {
			return duration
		}
	}
	return 0
}

func widthFromPost(post *postmodel.Post) int64 {
	if post == nil {
		return 0
	}
	if post.Width > 0 {
		return post.Width
	}
	for _, width := range []int64{
		post.DeviceInfo.Width,
		post.ArticleRenderProfile.Width,
		post.PrimaryHomepageSnapshot.Width,
	} {
		if width > 0 {
			return width
		}
	}
	return 0
}

func heightFromPost(post *postmodel.Post) int64 {
	if post == nil {
		return 0
	}
	if post.Height > 0 {
		return post.Height
	}
	for _, height := range []int64{
		post.DeviceInfo.Height,
		post.ArticleRenderProfile.Height,
		post.PrimaryHomepageSnapshot.Height,
	} {
		if height > 0 {
			return height
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

func NormalizePostObjectAnchors(post *postmodel.Post, payload map[string]any) error {
	if post == nil {
		return nil
	}
	if primaryHomepageID, exists := payload["primaryHomepageId"]; exists {
		post.PrimaryHomepageId = strings.TrimSpace(asString(primaryHomepageID))
	}
	if primaryHomepageType, exists := payload["primaryHomepageType"]; exists {
		post.PrimaryHomepageType = strings.TrimSpace(asString(primaryHomepageType))
	}
	if primaryHomepageSnapshot, exists := payload["primaryHomepageSnapshot"]; exists {
		decoded, err := decodePostHomepageSnapshot(primaryHomepageSnapshot)
		if err != nil {
			return rterr.NewInvalidArgument(
				rterr.ModuleContent,
				"主页快照格式不合法",
				err.Error(),
			)
		}
		post.PrimaryHomepageSnapshot = decoded
	}
	if entityRefs, exists := payload["entityRefs"]; exists {
		post.EntityRefs = normalizeRuntimeEntityRefs(asStringSlice(entityRefs))
	} else {
		post.EntityRefs = normalizeRuntimeEntityRefs(post.EntityRefs)
	}
	return nil
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
	normalized := strings.TrimSpace(strings.ToLower(value))
	switch normalized {
	case "", "public":
		return "public"
	case "private":
		return "private"
	default:
		return normalized
	}
}

func validateVisibility(value string) error {
	switch normalizeVisibility(value) {
	case "public", "private":
		return nil
	default:
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"内容可见性不合法",
			"visibility must be public or private",
		)
	}
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
	if assistantUsePolicy, exists := payload["assistantUsePolicy"]; exists {
		post.AssistantUsePolicy = normalizeAssistantUsePolicy(
			strings.TrimSpace(asString(assistantUsePolicy)),
		)
	}
	if err := NormalizePostObjectAnchors(post, payload); err != nil {
		return err
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
	if err := validateVisibility(post.Visibility); err != nil {
		return err
	}
	post.Visibility = normalizeVisibility(post.Visibility)
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

// visitedAtEarliestYear 是出行时间的下界年份。到访时间是作者声明的事实，
// 允许回溯多年补写游记，但明显不可能的年份（如 1900）只可能是端侧误传。
const visitedAtEarliestYear = 1970

// visitedAtFutureSkew 容忍端侧时钟与服务端的小幅偏差；超出即视为「计划出行」，
// 而计划不是到访事实，不得写进 visitedAt。
const visitedAtFutureSkew = 24 * time.Hour

// validateVisitedAt 守住出行时间的事实语义：可空，但一旦声明必须是过去的真实
// 到访时刻。未来时间会让「同地同期到访」交集把计划当成事实。
func validateVisitedAt(post *postmodel.Post) error {
	if post.VisitedAt.IsZero() {
		return nil
	}
	visited := post.VisitedAt.UTC()
	if visited.Year() < visitedAtEarliestYear {
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"出行时间不合法",
			"visitedAt is earlier than the supported range",
		)
	}
	if visited.After(time.Now().UTC().Add(visitedAtFutureSkew)) {
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"出行时间不能晚于当前时间",
			"visitedAt must not be in the future",
		)
	}
	post.VisitedAt = visited
	return nil
}

func validatePostPublicationPayload(post *postmodel.Post) error {
	if post.ContentIdentity == "" {
		post.ContentIdentity = normalizeContentIdentity(post.ContentType, "")
	}
	if post.AssistantUsePolicy == "" {
		post.AssistantUsePolicy = "inherit"
	}
	if err := validateContentIdentity(post.ContentType, post.ContentIdentity); err != nil {
		return err
	}
	if err := validateVisibility(post.Visibility); err != nil {
		return err
	}
	post.Visibility = normalizeVisibility(post.Visibility)
	if err := validateVisitedAt(post); err != nil {
		return err
	}
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
		if strings.TrimSpace(post.ThumbnailUrl) == "" &&
			strings.TrimSpace(post.CoverUrl) == "" {
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

func articleManifestAssetIDs(manifest postmodel.PostArticleAssetManifest) map[string]bool {
	result := map[string]bool{}
	for _, row := range manifest.Assets {
		id := strings.TrimSpace(row.AssetId)
		if id != "" {
			result[id] = true
		}
	}
	return result
}
