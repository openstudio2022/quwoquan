package comment

import (
	"context"
	"errors"
	"fmt"
	"slices"
	"strings"
	"time"

	contentgenerated "quwoquan_service/services/content-service/generated/content/comment"
	commentmodel "quwoquan_service/services/content-service/internal/content/comment/domain/model"
	commentports "quwoquan_service/services/content-service/internal/content/comment/domain/ports"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
)

const (
	maxCommentPage           = 100
	commentReplyPreviewLimit = 1
)

func (s *CommentService) ListComments(
	ctx context.Context,
	query ListCommentsQuery,
) (CommentPageSlice, error) {
	sortMode, sortValid := commentmodel.ParseSortMode(query.Sort)
	if !sortValid {
		return CommentPageSlice{}, contentgenerated.AppErrorFromCommentSortInvalid(
			fmt.Sprintf("unsupported comment sort %q", strings.TrimSpace(query.Sort)),
		)
	}
	blockedAuthorIDs, postOwnerBlocked, err := s.resolveCommentBlockScope(
		ctx,
		query.PostID,
		query.ActorID,
	)
	if err != nil {
		return CommentPageSlice{}, unavailableRead(err)
	}
	if postOwnerBlocked {
		return CommentPageSlice{Items: []CommentListItem{}}, nil
	}
	page, err := s.data.PostPage.ListByPost(
		ctx,
		strings.TrimSpace(query.PostID),
		commentports.PageRequest{
			Cursor:            strings.TrimSpace(query.Cursor),
			Limit:             pageLimit(query.Limit),
			Sort:              sortMode,
			ExcludedAuthorIDs: blockedAuthorIDs,
		},
	)
	if err != nil {
		return CommentPageSlice{}, unavailableRead(err)
	}
	items, err := s.projectItems(
		ctx,
		page.Items,
		query.ActorID,
		true,
		blockedAuthorIDs,
	)
	if err != nil {
		return CommentPageSlice{}, unavailableRead(err)
	}
	return CommentPageSlice{
		Items:      items,
		NextCursor: page.NextCursor,
		Total:      page.Total,
	}, nil
}

func (s *CommentService) ListReplies(
	ctx context.Context,
	query ListCommentRepliesQuery,
) (ReplyPageSlice, error) {
	blockedAuthorIDs, postOwnerBlocked, err := s.resolveCommentBlockScope(
		ctx,
		query.PostID,
		query.ActorID,
	)
	if err != nil {
		return ReplyPageSlice{}, unavailableRead(err)
	}
	if postOwnerBlocked {
		return ReplyPageSlice{Items: []CommentListItem{}}, nil
	}
	page, err := s.data.ReplyPage.ListReplies(
		ctx,
		strings.TrimSpace(query.PostID),
		strings.TrimSpace(query.ParentCommentID),
		commentports.PageRequest{
			Cursor:            strings.TrimSpace(query.Cursor),
			Limit:             pageLimit(query.Limit),
			ExcludedAuthorIDs: blockedAuthorIDs,
		},
	)
	if err != nil {
		return ReplyPageSlice{}, unavailableRead(err)
	}
	items, err := s.projectItems(
		ctx,
		page.Items,
		query.ActorID,
		false,
		blockedAuthorIDs,
	)
	if err != nil {
		return ReplyPageSlice{}, unavailableRead(err)
	}
	return ReplyPageSlice{
		Items:      items,
		NextCursor: page.NextCursor,
		Total:      page.Total,
	}, nil
}

func (s *CommentService) ListByAuthor(
	ctx context.Context,
	query ListCommentsByAuthorQuery,
) (AuthorCommentPageSlice, error) {
	actorID, err := requiredActorID(query.ActorID)
	if err != nil {
		return AuthorCommentPageSlice{}, err
	}
	page, err := s.data.AuthorPage.ListByAuthor(
		ctx,
		actorID,
		commentports.PageRequest{Cursor: strings.TrimSpace(query.Cursor), Limit: pageLimit(query.Limit)},
	)
	if err != nil {
		return AuthorCommentPageSlice{}, unavailableRead(err)
	}
	items, err := s.projectItems(ctx, page.Items, actorID, true, nil)
	if err != nil {
		return AuthorCommentPageSlice{}, unavailableRead(err)
	}
	return AuthorCommentPageSlice{
		Items:      items,
		NextCursor: page.NextCursor,
		Total:      page.Total,
	}, nil
}

func (s *CommentService) ListReceivedByPostAuthor(
	ctx context.Context,
	query ListReceivedCommentsQuery,
) (ReceivedCommentPageSlice, error) {
	actorID, err := requiredActorID(query.ActorID)
	if err != nil {
		return ReceivedCommentPageSlice{}, err
	}
	postIDs, err := s.data.PostRelation.ListOwnedPostIDs(ctx, actorID)
	if err != nil {
		return ReceivedCommentPageSlice{}, unavailableRead(err)
	}
	blockedAuthorIDs, err := s.viewerBlockedPersonaIDs(ctx, actorID)
	if err != nil {
		return ReceivedCommentPageSlice{}, unavailableRead(err)
	}
	page, err := s.data.ReceivedPage.ListReceivedByPostAuthor(
		ctx,
		actorID,
		postIDs,
		commentports.PageRequest{
			Cursor:            strings.TrimSpace(query.Cursor),
			Limit:             pageLimit(query.Limit),
			ExcludedAuthorIDs: blockedAuthorIDs,
		},
	)
	if err != nil {
		return ReceivedCommentPageSlice{}, unavailableRead(err)
	}
	items, err := s.projectItems(ctx, page.Items, actorID, true, blockedAuthorIDs)
	if err != nil {
		return ReceivedCommentPageSlice{}, unavailableRead(err)
	}
	return ReceivedCommentPageSlice{
		Items:      items,
		NextCursor: page.NextCursor,
		Total:      page.Total,
	}, nil
}

func (s *CommentService) resolveCommentBlockScope(
	ctx context.Context,
	postID string,
	viewerPersonaID string,
) ([]string, bool, error) {
	blockedAuthorIDs, err := s.viewerBlockedPersonaIDs(ctx, viewerPersonaID)
	if err != nil || len(blockedAuthorIDs) == 0 {
		return blockedAuthorIDs, false, err
	}
	ownership, found, err := s.data.PostRelation.FindPostOwnership(
		ctx,
		strings.TrimSpace(postID),
	)
	if err != nil {
		return nil, false, err
	}
	if !found {
		return blockedAuthorIDs, false, nil
	}
	return blockedAuthorIDs,
		slices.Contains(blockedAuthorIDs, strings.TrimSpace(ownership.AuthorID)),
		nil
}

func (s *CommentService) viewerBlockedPersonaIDs(
	ctx context.Context,
	viewerPersonaID string,
) ([]string, error) {
	viewerPersonaID = strings.TrimSpace(viewerPersonaID)
	if viewerPersonaID == "" {
		return nil, nil
	}
	if s == nil || s.data.ViewerBlocks == nil {
		return nil, errors.New("Comment viewer block reader is not configured")
	}
	blockedPersonaIDs, err := s.data.ViewerBlocks.ListBlockedPersonaIDs(
		ctx,
		viewerPersonaID,
	)
	if err != nil {
		return nil, fmt.Errorf("read Comment viewer block facts: %w", err)
	}
	unique := make(map[string]struct{}, len(blockedPersonaIDs))
	for _, personaID := range blockedPersonaIDs {
		personaID = strings.TrimSpace(personaID)
		if personaID != "" && personaID != viewerPersonaID {
			unique[personaID] = struct{}{}
		}
	}
	normalized := make([]string, 0, len(unique))
	for personaID := range unique {
		normalized = append(normalized, personaID)
	}
	slices.Sort(normalized)
	return normalized, nil
}

func pageLimit(limit int) int {
	if limit <= 0 {
		return 20
	}
	if limit > maxCommentPage {
		return maxCommentPage
	}
	return limit
}

// projectItems 组合 Comment、ContentReaction、MediaAsset 与 Post ownership 的
// 窄读投影。任何依赖读取失败都使 query fail closed，不产生默认零值伪成功。
func (s *CommentService) projectItems(
	ctx context.Context,
	readModels []commentmodel.ReadModel,
	actorID string,
	includeReplySummary bool,
	excludedAuthorIDs []string,
) ([]CommentListItem, error) {
	if len(readModels) == 0 {
		return []CommentListItem{}, nil
	}
	actorID = strings.TrimSpace(actorID)
	summaries := map[string]commentmodel.ReplySummary{}
	if includeReplySummary {
		parentIDs := make([]string, 0, len(readModels))
		for _, readModel := range readModels {
			if strings.TrimSpace(readModel.ParentCommentID) == "" {
				parentIDs = append(parentIDs, readModel.ID)
			}
		}
		var err error
		summaries, err = s.data.ReplySummary.ReadReplySummaries(
			ctx,
			parentIDs,
			commentReplyPreviewLimit,
			excludedAuthorIDs,
		)
		if err != nil {
			return nil, err
		}
	}

	allModels := make([]commentmodel.ReadModel, 0, len(readModels)*2)
	allModels = append(allModels, readModels...)
	for _, summary := range summaries {
		allModels = append(allModels, summary.Preview...)
	}
	commentIDs := uniqueCommentIDs(allModels)
	reactionCounts, err := s.data.Reactions.ReadCommentReactionCounts(ctx, commentIDs)
	if err != nil {
		return nil, err
	}
	viewerValues := map[string]reactiondomain.Value{}
	if actorID != "" {
		actor, actorErr := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, actorID)
		if actorErr != nil {
			return nil, actorErr
		}
		viewerValues, err = s.data.Reactions.ReadCommentReactionValues(ctx, actor, commentIDs)
		if err != nil {
			return nil, err
		}
	}
	ownerships, err := s.data.PostRelation.FindPostOwnerships(ctx, uniquePostIDs(allModels))
	if err != nil {
		return nil, err
	}
	attachments, err := s.data.Attachments.ReadCommentAttachments(ctx, uniqueAttachmentIDs(allModels))
	if err != nil {
		return nil, err
	}
	commentIDsByPostAuthor := map[string][]string{}
	for _, readModel := range allModels {
		postAuthorID := strings.TrimSpace(ownerships[readModel.PostID].AuthorID)
		if postAuthorID == "" || postAuthorID == strings.TrimSpace(readModel.AuthorID) {
			// 作者给自己的评论点赞不构成「作者赞过」信号。
			continue
		}
		commentIDsByPostAuthor[postAuthorID] = append(commentIDsByPostAuthor[postAuthorID], readModel.ID)
	}
	authorLikedFlags, err := s.data.Reactions.ReadAuthorLikedFlags(ctx, commentIDsByPostAuthor)
	if err != nil {
		return nil, err
	}
	viewerRelations := map[string]commentmodel.ViewerRelation{}
	if actorID != "" {
		viewerRelations, err = s.data.ViewerRelations.ReadViewerRelations(
			ctx,
			actorID,
			uniqueAuthorIDs(allModels),
		)
		if err != nil {
			return nil, err
		}
	}

	projectedByID := make(map[string]CommentListItem, len(allModels))
	for _, readModel := range allModels {
		projectedByID[readModel.ID] = projectCommentListItem(
			readModel,
			actorID,
			ownerships[readModel.PostID],
			reactionCounts[readModel.ID],
			viewerValues[readModel.ID],
			attachments,
			authorLikedFlags[readModel.ID],
			viewerRelations[readModel.AuthorID],
		)
	}
	items := make([]CommentListItem, 0, len(readModels))
	for _, readModel := range readModels {
		item := projectedByID[readModel.ID]
		if summary, found := summaries[readModel.ID]; found {
			item.ReplyCount = summary.Count
			item.ReplyNextCursor = summary.NextCursor
			item.ReplyPreview = make([]CommentListItem, 0, len(summary.Preview))
			for _, preview := range summary.Preview {
				item.ReplyPreview = append(item.ReplyPreview, projectedByID[preview.ID])
			}
		}
		items = append(items, item)
	}
	return items, nil
}

func projectCommentListItem(
	readModel commentmodel.ReadModel,
	actorID string,
	ownership commentmodel.PostOwnership,
	reactionCounts reactiondomain.CommentReactionCounts,
	viewerValue reactiondomain.Value,
	attachmentProjections map[string]commentmodel.AttachmentProjection,
	authorLiked bool,
	viewerRelation commentmodel.ViewerRelation,
) CommentListItem {
	isAuthor := actorID != "" && actorID == strings.TrimSpace(readModel.AuthorID)
	active := readModel.Status == commentmodel.StatusActive
	attachments := make([]CommentAttachmentSlice, 0, len(readModel.AttachmentMediaIDs))
	for _, mediaID := range readModel.AttachmentMediaIDs {
		projection, found := attachmentProjections[mediaID]
		if !found {
			projection = commentmodel.AttachmentProjection{MediaID: mediaID}
		}
		attachments = append(attachments, CommentAttachmentSlice{
			MediaID:   mediaID,
			MediaType: projection.MediaType,
			URL:       projection.URL,
			Width:     projection.Width,
			Height:    projection.Height,
			Available: projection.Available,
		})
	}
	viewerReaction := string(viewerValue)
	if viewerReaction == "" {
		viewerReaction = string(reactiondomain.ValueNone)
	}
	if viewerRelation == "" || isAuthor {
		viewerRelation = commentmodel.ViewerRelationNone
	}
	return CommentListItem{
		ID:                        readModel.ID,
		Version:                   readModel.Version,
		PostID:                    readModel.PostID,
		AuthorID:                  readModel.AuthorID,
		AuthorDisplayNameSnapshot: readModel.AuthorDisplayNameSnapshot,
		AuthorAvatarURLSnapshot:   readModel.AuthorAvatarURLSnapshot,
		PersonaContextVersion:     readModel.PersonaContextVersion,
		Content:                   readModel.Content,
		ReplyToCommentID:          readModel.ReplyToCommentID,
		ReplyToUserID:             readModel.ReplyToUserID,
		ParentCommentID:           readModel.ParentCommentID,
		AttachmentMediaIDs:        cloneStrings(readModel.AttachmentMediaIDs),
		Attachments:               attachments,
		Mentions:                  cloneMentions(readModel.Mentions),
		AssistantMentioned:        readModel.AssistantMentioned,
		AssistantReplySource:      readModel.AssistantReplySource,
		AssistantCorrectionStatus: readModel.AssistantCorrectionStatus,
		AuthorIPLocation:          readModel.AuthorIPLocation,
		Status:                    readModel.Status,
		IsPinned:                  readModel.IsPinned,
		PinnedAt:                  cloneTime(readModel.PinnedAt),
		CreatedAt:                 readModel.CreatedAt.UTC(),
		UpdatedAt:                 readModel.UpdatedAt.UTC(),
		DeletedAt:                 cloneTime(readModel.DeletedAt),
		ReplyPreview:              []CommentListItem{},
		LikeCount:                 reactionCounts.LikeCount,
		DislikeCount:              reactionCounts.DislikeCount,
		ViewerReaction:            viewerReaction,
		AuthorLiked:               authorLiked,
		ViewerRelation:            string(viewerRelation),
		IsAuthor:                  isAuthor,
		CanDelete:                 active && isAuthor,
		CanReply:                  active && actorID != "",
		CanReport:                 active && actorID != "" && !isAuthor,
		CanPin: active && actorID != "" &&
			strings.TrimSpace(readModel.ParentCommentID) == "" &&
			ownership.Active && strings.TrimSpace(ownership.AuthorID) == actorID,
	}
}

func uniqueCommentIDs(readModels []commentmodel.ReadModel) []string {
	return uniqueStringsFromReadModels(readModels, func(item commentmodel.ReadModel) []string {
		return []string{item.ID}
	})
}

func uniquePostIDs(readModels []commentmodel.ReadModel) []string {
	return uniqueStringsFromReadModels(readModels, func(item commentmodel.ReadModel) []string {
		return []string{item.PostID}
	})
}

func uniqueAttachmentIDs(readModels []commentmodel.ReadModel) []string {
	return uniqueStringsFromReadModels(readModels, func(item commentmodel.ReadModel) []string {
		return item.AttachmentMediaIDs
	})
}

func uniqueAuthorIDs(readModels []commentmodel.ReadModel) []string {
	return uniqueStringsFromReadModels(readModels, func(item commentmodel.ReadModel) []string {
		return []string{item.AuthorID}
	})
}

func uniqueStringsFromReadModels(
	readModels []commentmodel.ReadModel,
	selectValues func(commentmodel.ReadModel) []string,
) []string {
	seen := map[string]struct{}{}
	values := make([]string, 0)
	for _, readModel := range readModels {
		for _, value := range selectValues(readModel) {
			value = strings.TrimSpace(value)
			if value == "" {
				continue
			}
			if _, found := seen[value]; found {
				continue
			}
			seen[value] = struct{}{}
			values = append(values, value)
		}
	}
	return values
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := value.UTC()
	return &cloned
}
