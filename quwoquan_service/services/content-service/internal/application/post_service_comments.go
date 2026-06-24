package application

import (
	"context"
	"fmt"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/repository"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"strings"
	"time"
)

func (s *PostService) AddComment(
	ctx context.Context,
	postID string,
	userID string,
	content string,
	replyToCommentID string,
	authorID string,
	personaContextVersion string,
	attachmentMediaIDs []string,
	mentions []map[string]any,
) (map[string]any, int64, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return nil, 0, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	userID = strings.TrimSpace(userID)
	authorID = strings.TrimSpace(authorID)
	if authorID == "" {
		authorID = userID
	}
	if authorID == "" {
		return nil, 0, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"authorId 不能为空",
			"missing comment authorId/subAccountId",
		)
	}
	content = strings.TrimSpace(content)
	if content == "" {
		return nil, 0, rterr.NewInvalidArgument(rterr.ModuleContent, "评论内容不能为空", "empty comment content")
	}
	contentRunes := []rune(content)
	if len(contentRunes) > s.commentMaxLen {
		return nil, 0, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "comment_too_long"),
			fmt.Sprintf("评论超出字数限制（最多 %d 字）", s.commentMaxLen),
			fmt.Sprintf("comment length %d exceeds max %d", len(contentRunes), s.commentMaxLen),
		)
	}

	replyToCommentID = strings.TrimSpace(replyToCommentID)
	var replyToUserId string
	var parentCommentID string
	now := time.Now().UTC()
	if replyToCommentID != "" {
		target, found := s.commentStore.FindByID(ctx, replyToCommentID)
		if !found {
			return nil, 0, rterr.NewAppError(
				rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "comment_not_found"),
				"回复目标不存在",
				"reply target comment not found",
			)
		}
		replyToUserId = strings.TrimSpace(target.AuthorId)
		parentCommentID = strings.TrimSpace(target.ParentCommentId)
		if parentCommentID == "" {
			parentCommentID = replyToCommentID
		}
		// 回复数变化影响父评论综合分：原子 +1 并落写时确定性快照分。
		if parent, pok := s.commentStore.FindByID(ctx, parentCommentID); pok {
			projectedParent := *parent
			projectedParent.ReplyCount = parent.ReplyCount + 1
			newScore := commentRecommendedScoreModel(projectedParent, now)
			if _, _, err := s.commentStore.AdjustReplyCount(ctx, parentCommentID, 1, newScore); err != nil {
				s.logger.Warn("AddComment: adjust parent reply count failed", "error", err.Error())
			}
		}
	}

	// 媒体附件绑定仍依赖进程内存的 mediaAssets，单独短临界区加锁。
	attachmentIDs, attachments, err := s.prepareCommentAttachments(post.ID, authorID, attachmentMediaIDs)
	if err != nil {
		return nil, 0, err
	}
	normalizedMentions := normalizeCommentMentions(mentions)
	assistantMentioned := commentHasAssistantMention(normalizedMentions)

	// 评论属地：创建时按受信客户端 IP 解析省级展示串并落库快照；
	// 解析不出则留空（前端不展示），绝不臆造属地。
	ipLocation := ""
	if s.ipResolver != nil {
		ipLocation = strings.TrimSpace(s.ipResolver.Resolve(clientIPFromContext(ctx)))
	}
	comment := postmodel.Comment{
		ID:                    fmt.Sprintf("comment_%d", now.UnixNano()),
		PostId:                post.ID,
		AuthorId:              authorID,
		PersonaContextVersion: asInt64Flexible(personaContextVersion),
		Content:               content,
		IpLocation:            ipLocation,
		ReplyToCommentId:      replyToCommentID,
		ReplyToUserId:         replyToUserId,
		ParentCommentId:       parentCommentID,
		AttachmentMediaIds:    attachmentIDs,
		Attachments:           attachments,
		Mentions:              normalizedMentions,
		AssistantMentioned:    assistantMentioned,
		ReplyCount:            0,
		LikeCount:             0,
		DislikeCount:          0,
		ViewerReaction:        "none",
		RecommendedScore:      0,
		Status:                "visible",
		CanDelete:             true,
		CanReply:              true,
		CanReport:             false,
		CreatedAt:             now,
	}
	// 综合分写时确定性预计算并落字段：排序只读快照值，消除读路径 time.Since 漂移。
	comment.RecommendedScore = commentRecommendedScoreModel(comment, now)
	if err := s.commentStore.Create(ctx, &comment); err != nil {
		return nil, 0, rterr.NewUnavailable(
			rterr.ModuleContent,
			"评论保存失败，请稍后重试",
			"comment persist failed: "+err.Error(),
		)
	}

	// 计数热路径：单字段原子 $inc(+1)，消除每次增删的全量 CountDocuments + 整文档
	// 改写热写。单一真相源仍是评论集 DB count；Post.commentCount 仅为去规范化加速
	// 器，GetCounters 读路径按权威 count 机会式自愈漂移。$inc 失败才回退权威对账。
	commentCount, ok, err := s.store.AdjustCommentCount(ctx, post.ID, 1)
	if err != nil || !ok {
		if err != nil {
			s.logger.Warn("AddComment: adjust comment count failed", "postId", post.ID, "error", err.Error())
		}
		commentCount = s.reconcilePostCommentCount(ctx, post.ID)
	}
	projectedComment := s.projectCommentSingle(ctx, comment, authorID, true)

	if s.publisher != nil {
		featurePayload := commentFeaturePayload(*post, content, parentCommentID, replyToUserId, attachments)
		_ = s.publisher.Publish(ctx, repository.DomainEvent{
			Type:          "CommentCreated",
			AggregateType: "Post",
			AggregateID:   post.ID,
			Payload: map[string]any{
				"commentId":             comment.ID,
				"postId":                post.ID,
				"authorId":              authorID,
				"content":               content,
				"commentLength":         len(contentRunes),
				"replyDepth":            commentReplyDepth(parentCommentID),
				"replyToUserId":         replyToUserId,
				"parentCommentId":       parentCommentID,
				"targetAuthorId":        featurePayload["targetAuthorId"],
				"attachmentMediaIds":    attachmentIDs,
				"attachmentTypes":       featurePayload["attachmentTypes"],
				"mentions":              normalizedMentions,
				"tagRefs":               featurePayload["tagRefs"],
				"entityRefs":            featurePayload["entityRefs"],
				"sentimentLabel":        featurePayload["sentimentLabel"],
				"intentLabel":           featurePayload["intentLabel"],
				"moderationLabels":      featurePayload["moderationLabels"],
				"intersectionDimension": featurePayload["intersectionDimension"],
			},
			OccurredAt: now.Format(time.RFC3339),
		})
	}

	return projectedComment, commentCount, nil
}
