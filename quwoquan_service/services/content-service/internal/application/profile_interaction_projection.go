package application

import (
	"fmt"
	"strings"
	"time"

	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

type profileInteractionProjectionInput struct {
	ActivityID         string
	ActivityType       string
	Direction          string
	ActorID            string
	TargetSubAccountID string
	Post               *postmodel.Post
	Comment            *postmodel.Comment
	// ViewerReaction 是当前 viewer 对该互动评论的真实三态反应（none/like/dislike），
	// 由调用方经 ReactionStore 批量解析后注入；非评论互动恒为 none。
	ViewerReaction string
	CreatedAt      time.Time
}

func buildProfileInteractionActivityView(input profileInteractionProjectionInput) postmodel.ProfileInteractionActivityView {
	summary := ""
	contentType := ""
	targetContentID := ""
	if input.Post != nil {
		summary = summarizeInteractionTarget(input.Post)
		contentType = input.Post.ContentType
		targetContentID = input.Post.ID
	}
	activityType := strings.TrimSpace(input.ActivityType)
	direction := strings.TrimSpace(input.Direction)
	if direction == "" {
		direction = "received"
	}
	commentText := ""
	if input.Comment != nil {
		commentText = strings.TrimSpace(input.Comment.Content)
	}
	commentKind := profileInteractionCommentKind(input.Comment)
	commentID, parentCommentID := profileInteractionCommentIdentity(input.Comment)
	viewerReaction := normalizeProfileInteractionViewerReaction(input.ViewerReaction)
	if activityType != "comment" {
		commentKind = "none"
		commentID = ""
		parentCommentID = ""
		viewerReaction = "none"
	}
	actorName, actorAvatarURL := profileInteractionActorSnapshot(input.ActorID, input.Post, input.Comment)
	targetName, targetAvatarURL := profileInteractionTargetSnapshot(input.TargetSubAccountID, input.Post)
	displaySubAccountID := strings.TrimSpace(input.ActorID)
	displayName := actorName
	displayAvatarURL := actorAvatarURL
	if direction == "sent" {
		displaySubAccountID = strings.TrimSpace(input.TargetSubAccountID)
		displayName = targetName
		displayAvatarURL = targetAvatarURL
	}
	previewUnavailable := profileInteractionPreviewUnavailable(input.Post)
	previewRouteID := ""
	if !previewUnavailable && targetContentID != "" {
		previewRouteID = "workBrowser"
	}
	previewText := summary
	if previewUnavailable {
		previewText = ""
	}
	if input.CreatedAt.IsZero() {
		input.CreatedAt = time.Now().UTC()
	}
	return postmodel.ProfileInteractionActivityView{
		ActivityId:           strings.TrimSpace(input.ActivityID),
		ActivityType:         activityType,
		Direction:            direction,
		CommentKind:          commentKind,
		CommentId:            commentID,
		ParentCommentId:      parentCommentID,
		// viewer 对该互动评论的真实三态反应（R-CMT01：由 ReactionStore 解析后注入）。
		ViewerReaction:       viewerReaction,
		ActorSubAccountId:    strings.TrimSpace(input.ActorID),
		ActorDisplayName:     actorName,
		ActorAvatarUrl:       actorAvatarURL,
		TargetSubAccountId:   strings.TrimSpace(input.TargetSubAccountID),
		TargetContentId:      targetContentID,
		TargetContentType:    contentType,
		TargetContentSummary: summary,
		DisplaySubAccountId:  displaySubAccountID,
		DisplayName:          displayName,
		DisplayAvatarUrl:     displayAvatarURL,
		DisplayUserRouteId:   "userProfile",
		PrimaryText:          profileInteractionPrimaryText(activityType, direction, commentKind, commentText),
		ContextText:          profileInteractionContextText(input.Comment),
		PreviewMediaKind:     profileInteractionPreviewMediaKind(input.Post),
		PreviewImageUrl:      profileInteractionPreviewImageURL(input.Post),
		PreviewText:          previewText,
		PreviewUnavailable:   previewUnavailable,
		PreviewObjectId:      targetContentID,
		PreviewRouteId:       previewRouteID,
		FilterKeys:           profileInteractionFilterKeys(activityType),
		CreatedAt:            input.CreatedAt,
	}
}

func profileInteractionActorSnapshot(actorID string, post *postmodel.Post, comment *postmodel.Comment) (string, string) {
	actorID = strings.TrimSpace(actorID)
	if comment != nil && strings.TrimSpace(comment.AuthorId) == actorID {
		name := strings.TrimSpace(comment.AuthorDisplayNameSnapshot)
		avatarURL := strings.TrimSpace(comment.AuthorAvatarUrlSnapshot)
		return defaultString(name, actorID), avatarURL
	}
	if post != nil && strings.TrimSpace(post.AuthorId) == actorID {
		return defaultString(strings.TrimSpace(post.AuthorDisplayNameSnapshot), actorID),
			strings.TrimSpace(post.AuthorAvatarUrlSnapshot)
	}
	return actorID, ""
}

func profileInteractionTargetSnapshot(targetSubAccountID string, post *postmodel.Post) (string, string) {
	targetSubAccountID = strings.TrimSpace(targetSubAccountID)
	if post != nil && strings.TrimSpace(post.AuthorId) == targetSubAccountID {
		return defaultString(strings.TrimSpace(post.AuthorDisplayNameSnapshot), targetSubAccountID),
			strings.TrimSpace(post.AuthorAvatarUrlSnapshot)
	}
	return targetSubAccountID, ""
}

func profileInteractionPrimaryText(activityType, direction, commentKind, commentText string) string {
	switch strings.TrimSpace(activityType) {
	case "like":
		if direction == "sent" {
			return "你点赞了TA的记录"
		}
		return "点赞了你的记录"
	case "comment":
		return profileInteractionCommentPrimaryText(direction, commentKind, commentText)
	case "share":
		if direction == "sent" {
			return "你转发了TA的记录"
		}
		return "转发了你的记录"
	default:
		return summarizeInteractionActivityFallback(commentText)
	}
}

func profileInteractionCommentPrimaryText(direction, commentKind, commentText string) string {
	if commentText == "" {
		if direction == "sent" {
			return "你评论了TA的记录"
		}
		return "评论了你的记录"
	}
	if direction == "sent" {
		if commentKind == "reply" {
			return fmt.Sprintf("你回复了TA：%s", commentText)
		}
		return fmt.Sprintf("你评论了TA的记录：%s", commentText)
	}
	if commentKind == "reply" {
		return fmt.Sprintf("回复了你：%s", commentText)
	}
	return fmt.Sprintf("评论了你的记录：%s", commentText)
}

func summarizeInteractionActivityFallback(commentText string) string {
	if strings.TrimSpace(commentText) != "" {
		return strings.TrimSpace(commentText)
	}
	return "互动了这条记录"
}

func profileInteractionContextText(comment *postmodel.Comment) string {
	if comment == nil {
		return ""
	}
	replyToUserID := strings.TrimSpace(comment.ReplyToUserId)
	if replyToUserID == "" {
		return ""
	}
	return fmt.Sprintf("回复 %s", replyToUserID)
}

// normalizeProfileInteractionViewerReaction coerces a raw reaction string into a
// valid three-state value (none/like/dislike), defaulting unknown/empty to none.
func normalizeProfileInteractionViewerReaction(raw string) string {
	switch strings.TrimSpace(raw) {
	case "like":
		return "like"
	case "dislike":
		return "dislike"
	default:
		return "none"
	}
}

// profileInteractionCommentIdentity 解析互动评论的稳定标识：
// commentID 为本条评论/回复 id（用于深链精确定位），
// parentCommentID 为其顶级评论 id（回复场景用于在评论区高亮父评论行）。
func profileInteractionCommentIdentity(comment *postmodel.Comment) (string, string) {
	if comment == nil {
		return "", ""
	}
	return strings.TrimSpace(comment.ID), strings.TrimSpace(comment.ParentCommentId)
}

func profileInteractionCommentKind(comment *postmodel.Comment) string {
	if comment == nil {
		return "none"
	}
	if strings.TrimSpace(comment.ParentCommentId) != "" ||
		strings.TrimSpace(comment.ReplyToCommentId) != "" ||
		strings.TrimSpace(comment.ReplyToUserId) != "" {
		return "reply"
	}
	return "comment"
}

func profileInteractionFilterKeys(activityType string) []string {
	key := "all"
	switch strings.TrimSpace(activityType) {
	case "like":
		key = "likes"
	case "comment":
		key = "comments"
	case "share":
		key = "shares"
	}
	if key == "all" {
		return []string{"all"}
	}
	return []string{"all", key}
}

func profileInteractionPreviewUnavailable(post *postmodel.Post) bool {
	if post == nil {
		return true
	}
	status := strings.TrimSpace(post.Status)
	return !post.DeletedAt.IsZero() || status == "deleted" || status == "removed"
}

func profileInteractionPreviewMediaKind(post *postmodel.Post) string {
	if post == nil || profileInteractionPreviewUnavailable(post) {
		return "none"
	}
	contentType := strings.TrimSpace(post.ContentType)
	switch contentType {
	case "video":
		return "video"
	case "image", "photo":
		return "image"
	case "article", "micro", "text":
		return "text"
	default:
		if profileInteractionPreviewImageURL(post) != "" {
			return "image"
		}
		if summarizeInteractionTarget(post) != "" {
			return "text"
		}
		return "none"
	}
}

func profileInteractionPreviewImageURL(post *postmodel.Post) string {
	if post == nil || profileInteractionPreviewUnavailable(post) {
		return ""
	}
	if coverURL := strings.TrimSpace(post.CoverUrl); coverURL != "" {
		return coverURL
	}
	for _, mediaURL := range post.MediaUrls {
		if value := strings.TrimSpace(mediaURL); value != "" {
			return value
		}
	}
	return ""
}

func summarizeInteractionTarget(post *postmodel.Post) string {
	if post == nil {
		return ""
	}
	if summary := strings.TrimSpace(post.Summary); summary != "" {
		return summary
	}
	if title := strings.TrimSpace(post.Title); title != "" {
		return title
	}
	body := strings.TrimSpace(post.Body)
	bodyRunes := []rune(body)
	if len(bodyRunes) > 60 {
		return string(bodyRunes[:60])
	}
	return body
}
