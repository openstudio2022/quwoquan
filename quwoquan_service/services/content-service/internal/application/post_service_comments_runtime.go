package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"math"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/repository"
	commentdomain "quwoquan_service/services/content-service/internal/domain/comment"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"regexp"
	"strings"
	"time"
)

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
