package comment

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"slices"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/content-service/internal/application/commandmeta"
	commentmodel "quwoquan_service/services/content-service/internal/domain/comment/model"
	commentports "quwoquan_service/services/content-service/internal/domain/comment/ports"
	reactiondomain "quwoquan_service/services/content-service/internal/domain/reaction"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

const (
	commentReceiptTTL = 24 * time.Hour
	maxCommentPage    = 100

	commentCreatedEventType          = "CommentCreated"
	commentDeletedEventType          = "CommentDeleted"
	commentPinChangedEventType       = "CommentPinChanged"
	commentAttachmentsBoundEventType = "CommentAttachmentsBound"
)

// CommentService is the object-specific application service. All dependencies
// are Comment domain ports; it neither imports infrastructure nor PostService.
type CommentService struct {
	data DataPorts
	now  func() time.Time
}

func NewCommentService(data DataPorts) *CommentService {
	if data.Aggregate == nil ||
		data.PostPage == nil ||
		data.ReplyPage == nil ||
		data.ReplySummary == nil ||
		data.AuthorPage == nil ||
		data.ReceivedPage == nil ||
		data.Counts == nil ||
		data.Relations == nil ||
		data.PostRelation == nil ||
		data.Attachments == nil ||
		data.Reactions == nil {
		panic("CommentService requires all object-specific data ports")
	}
	return &CommentService{
		data: data,
		now:  time.Now,
	}
}

func (s *CommentService) CreateComment(
	ctx context.Context,
	command CreateCommentCommand,
) (CommentCommandResult, error) {
	actorID, err := requiredActorID(command.ActorID)
	if err != nil {
		return CommentCommandResult{}, err
	}
	command.ActorID = actorID
	commandDigest := createCommandDigest(command)
	if replayed, found, err := s.replay(ctx, actorID, "CreateComment", commandDigest); err != nil || found {
		return replayed, err
	}
	postID := strings.TrimSpace(command.PostID)
	post, found, err := s.data.PostRelation.FindPostOwnership(ctx, postID)
	if err != nil {
		return CommentCommandResult{}, unavailable(err)
	}
	if !found || !post.Active {
		return CommentCommandResult{}, contentgenerated.AppErrorFromPostNotFound(
			fmt.Sprintf("post %s is unavailable for comment creation", postID),
		)
	}

	params := commentmodel.CreateParams{
		PostID:                    postID,
		AuthorID:                  actorID,
		AuthorDisplayNameSnapshot: command.AuthorDisplayNameSnapshot,
		AuthorAvatarURLSnapshot:   command.AuthorAvatarURLSnapshot,
		PersonaContextVersion:     command.PersonaContextVersion,
		Content:                   command.Content,
		AttachmentMediaIDs:        cloneStrings(command.AttachmentMediaIDs),
		Mentions:                  cloneMentions(command.Mentions),
		AssistantMentioned:        containsAssistantMention(command.Mentions),
		Now:                       s.now().UTC(),
	}
	if replyID := strings.TrimSpace(command.ReplyToCommentID); replyID != "" {
		target, targetFound, relationErr := s.data.Relations.FindReplyTarget(ctx, replyID)
		if relationErr != nil {
			return CommentCommandResult{}, unavailable(relationErr)
		}
		if !targetFound ||
			target.Status != commentmodel.StatusActive ||
			strings.TrimSpace(target.PostID) != postID {
			return CommentCommandResult{}, invalidArgument("reply target is absent, deleted, or belongs to another post")
		}
		params.ReplyToCommentID = target.ID
		params.ReplyToUserID = target.AuthorID
		params.ParentCommentID = target.ParentCommentID
		if params.ParentCommentID == "" {
			params.ParentCommentID = target.ID
		}
	}
	if err := s.data.Attachments.ValidateCommentAttachments(ctx, actorID, params.AttachmentMediaIDs); err != nil {
		return CommentCommandResult{}, mapDomainError(err)
	}

	commentID, err := newIdentifier("cmt")
	if err != nil {
		return CommentCommandResult{}, unavailable(err)
	}
	params.ID = commentID
	aggregate, err := commentmodel.Create(params)
	if err != nil {
		return CommentCommandResult{}, mapDomainError(err)
	}
	payload, err := json.Marshal(commentCreatedEvent{
		CommentID:        aggregate.ID(),
		Version:          aggregate.Version(),
		PostID:           params.PostID,
		AuthorID:         actorID,
		ReplyToCommentID: params.ReplyToCommentID,
		ReplyToUserID:    params.ReplyToUserID,
		ParentCommentID:  params.ParentCommentID,
		CreatedAt:        params.Now.UTC(),
	})
	if err != nil {
		return CommentCommandResult{}, unavailable(err)
	}
	return s.commit(
		ctx,
		actorID,
		aggregate,
		0,
		"CreateComment",
		commandDigest,
		commentCreatedEventType,
		payload,
		params.Now,
	)
}

func (s *CommentService) DeleteComment(
	ctx context.Context,
	command DeleteCommentCommand,
) (CommentCommandResult, error) {
	actorID, err := requiredActorID(command.ActorID)
	if err != nil {
		return CommentCommandResult{}, err
	}
	command.ActorID = actorID
	commandDigest := deleteCommandDigest(command)
	if replayed, found, err := s.replay(ctx, actorID, "DeleteComment", commandDigest); err != nil || found {
		return replayed, err
	}
	for attempt := 0; attempt < 3; attempt++ {
		aggregate, found, loadErr := s.load(ctx, command.CommentID)
		if loadErr != nil {
			return CommentCommandResult{}, loadErr
		}
		if !found || aggregate.Snapshot().PostID != strings.TrimSpace(command.PostID) {
			return CommentCommandResult{}, commentNotFound(command.CommentID)
		}
		if aggregate.Status() == commentmodel.StatusDeleted {
			return s.recordIdempotentReceipt(
				ctx,
				actorID,
				aggregate,
				"DeleteComment",
				commandDigest,
			)
		}
		expectedVersion := aggregate.Version()
		now := s.now().UTC()
		if deleteErr := aggregate.Delete(actorID, now); deleteErr != nil {
			return CommentCommandResult{}, mapDomainError(deleteErr)
		}
		snapshot := aggregate.Snapshot()
		payload, marshalErr := json.Marshal(commentDeletedEvent{
			CommentID:       snapshot.ID,
			Version:         snapshot.Version,
			PostID:          snapshot.PostID,
			AuthorID:        snapshot.AuthorID,
			ParentCommentID: snapshot.ParentCommentID,
			DeletedAt:       now,
		})
		if marshalErr != nil {
			return CommentCommandResult{}, unavailable(marshalErr)
		}
		result, commitErr := s.commit(
			ctx,
			actorID,
			aggregate,
			expectedVersion,
			"DeleteComment",
			commandDigest,
			commentDeletedEventType,
			payload,
			now,
		)
		if commitErr == nil {
			return result, nil
		}
		if !isCommentVersionConflict(commitErr) || attempt == 2 {
			if isCommentVersionConflict(commitErr) {
				return CommentCommandResult{}, contentgenerated.AppErrorFromVersionConflict(
					"comment changed repeatedly while applying delete intent",
				)
			}
			return CommentCommandResult{}, commitErr
		}
	}
	panic("unreachable Comment delete retry")
}

func (s *CommentService) PinComment(
	ctx context.Context,
	command ChangeCommentPinCommand,
) (CommentCommandResult, error) {
	command.Pinned = true
	return s.changePin(ctx, "PinComment", command)
}

func (s *CommentService) UnpinComment(
	ctx context.Context,
	command ChangeCommentPinCommand,
) (CommentCommandResult, error) {
	command.Pinned = false
	return s.changePin(ctx, "UnpinComment", command)
}

func (s *CommentService) changePin(
	ctx context.Context,
	commandName string,
	command ChangeCommentPinCommand,
) (CommentCommandResult, error) {
	actorID, err := requiredActorID(command.ActorID)
	if err != nil {
		return CommentCommandResult{}, err
	}
	command.ActorID = actorID
	commandDigest := pinCommandDigest(commandName, command)
	if replayed, found, err := s.replay(ctx, actorID, commandName, commandDigest); err != nil || found {
		return replayed, err
	}
	ownership, ownershipFound, err := s.data.PostRelation.FindPostOwnership(
		ctx,
		strings.TrimSpace(command.PostID),
	)
	if err != nil {
		return CommentCommandResult{}, unavailable(err)
	}
	if !ownershipFound || !ownership.Active {
		return CommentCommandResult{}, contentgenerated.AppErrorFromPostNotFound(
			fmt.Sprintf("post %s is unavailable for comment pin", command.PostID),
		)
	}
	for attempt := 0; attempt < 3; attempt++ {
		aggregate, found, loadErr := s.load(ctx, command.CommentID)
		if loadErr != nil {
			return CommentCommandResult{}, loadErr
		}
		if !found || aggregate.Snapshot().PostID != strings.TrimSpace(command.PostID) {
			return CommentCommandResult{}, commentNotFound(command.CommentID)
		}
		if aggregate.Snapshot().IsPinned == command.Pinned {
			return s.recordIdempotentReceipt(
				ctx,
				actorID,
				aggregate,
				commandName,
				commandDigest,
			)
		}
		expectedVersion := aggregate.Version()
		now := s.now().UTC()
		if pinErr := aggregate.ChangePin(actorID, ownership.AuthorID, command.Pinned, now); pinErr != nil {
			return CommentCommandResult{}, mapDomainError(pinErr)
		}
		snapshot := aggregate.Snapshot()
		payload, marshalErr := json.Marshal(commentPinChangedEvent{
			CommentID:  snapshot.ID,
			Version:    snapshot.Version,
			PostID:     snapshot.PostID,
			OperatorID: actorID,
			IsPinned:   snapshot.IsPinned,
			PinnedAt:   snapshot.PinnedAt,
		})
		if marshalErr != nil {
			return CommentCommandResult{}, unavailable(marshalErr)
		}
		result, commitErr := s.commit(
			ctx,
			actorID,
			aggregate,
			expectedVersion,
			commandName,
			commandDigest,
			commentPinChangedEventType,
			payload,
			now,
		)
		if commitErr == nil {
			return result, nil
		}
		if !isCommentVersionConflict(commitErr) || attempt == 2 {
			if isCommentVersionConflict(commitErr) {
				return CommentCommandResult{}, contentgenerated.AppErrorFromVersionConflict(
					"comment changed repeatedly while applying pin intent",
				)
			}
			return CommentCommandResult{}, commitErr
		}
	}
	panic("unreachable Comment pin retry")
}

func (s *CommentService) BindAttachments(
	ctx context.Context,
	command BindCommentAttachmentsCommand,
) (CommentCommandResult, error) {
	actorID, err := requiredActorID(command.ActorID)
	if err != nil {
		return CommentCommandResult{}, err
	}
	command.ActorID = actorID
	commandDigest := bindAttachmentsCommandDigest(command)
	if replayed, found, err := s.replay(ctx, actorID, "BindCommentAttachments", commandDigest); err != nil || found {
		return replayed, err
	}
	if err := s.data.Attachments.ValidateCommentAttachments(ctx, actorID, command.AttachmentMediaIDs); err != nil {
		return CommentCommandResult{}, mapDomainError(err)
	}
	for attempt := 0; attempt < 3; attempt++ {
		aggregate, found, loadErr := s.load(ctx, command.CommentID)
		if loadErr != nil {
			return CommentCommandResult{}, loadErr
		}
		if !found {
			return CommentCommandResult{}, commentNotFound(command.CommentID)
		}
		if slices.Equal(
			aggregate.Snapshot().AttachmentMediaIDs,
			command.AttachmentMediaIDs,
		) {
			return s.recordIdempotentReceipt(
				ctx,
				actorID,
				aggregate,
				"BindCommentAttachments",
				commandDigest,
			)
		}
		expectedVersion := aggregate.Version()
		now := s.now().UTC()
		if bindErr := aggregate.BindAttachments(actorID, command.AttachmentMediaIDs, now); bindErr != nil {
			return CommentCommandResult{}, mapDomainError(bindErr)
		}
		snapshot := aggregate.Snapshot()
		payload, marshalErr := json.Marshal(commentAttachmentsBoundEvent{
			CommentID:          snapshot.ID,
			Version:            snapshot.Version,
			PostID:             snapshot.PostID,
			AuthorID:           snapshot.AuthorID,
			AttachmentMediaIDs: cloneStrings(snapshot.AttachmentMediaIDs),
		})
		if marshalErr != nil {
			return CommentCommandResult{}, unavailable(marshalErr)
		}
		result, commitErr := s.commit(
			ctx,
			actorID,
			aggregate,
			expectedVersion,
			"BindCommentAttachments",
			commandDigest,
			commentAttachmentsBoundEventType,
			payload,
			now,
		)
		if commitErr == nil {
			return result, nil
		}
		if !isCommentVersionConflict(commitErr) || attempt == 2 {
			if isCommentVersionConflict(commitErr) {
				return CommentCommandResult{}, contentgenerated.AppErrorFromVersionConflict(
					"comment changed repeatedly while applying attachment intent",
				)
			}
			return CommentCommandResult{}, commitErr
		}
	}
	panic("unreachable Comment attachment retry")
}

func (s *CommentService) ListComments(
	ctx context.Context,
	query ListCommentsQuery,
) (CommentPageSlice, error) {
	page, err := s.data.PostPage.ListByPost(
		ctx,
		strings.TrimSpace(query.PostID),
		commentports.PageRequest{Cursor: strings.TrimSpace(query.Cursor), Limit: pageLimit(query.Limit)},
	)
	if err != nil {
		return CommentPageSlice{}, unavailableRead(err)
	}
	items, err := s.projectItems(ctx, page.Items, query.ActorID, true)
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
	page, err := s.data.ReplyPage.ListReplies(
		ctx,
		strings.TrimSpace(query.PostID),
		strings.TrimSpace(query.ParentCommentID),
		commentports.PageRequest{Cursor: strings.TrimSpace(query.Cursor), Limit: pageLimit(query.Limit)},
	)
	if err != nil {
		return ReplyPageSlice{}, unavailableRead(err)
	}
	items, err := s.projectItems(ctx, page.Items, query.ActorID, false)
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
	items, err := s.projectItems(ctx, page.Items, actorID, true)
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
	page, err := s.data.ReceivedPage.ListReceivedByPostAuthor(
		ctx,
		actorID,
		postIDs,
		commentports.PageRequest{Cursor: strings.TrimSpace(query.Cursor), Limit: pageLimit(query.Limit)},
	)
	if err != nil {
		return ReceivedCommentPageSlice{}, unavailableRead(err)
	}
	items, err := s.projectItems(ctx, page.Items, actorID, true)
	if err != nil {
		return ReceivedCommentPageSlice{}, unavailableRead(err)
	}
	return ReceivedCommentPageSlice{
		Items:      items,
		NextCursor: page.NextCursor,
		Total:      page.Total,
	}, nil
}

func (s *CommentService) load(
	ctx context.Context,
	commentID string,
) (*commentmodel.Comment, bool, error) {
	aggregate, found, err := s.data.Aggregate.Load(ctx, strings.TrimSpace(commentID))
	if err != nil {
		return nil, false, unavailable(err)
	}
	return aggregate, found, nil
}

func (s *CommentService) replay(
	ctx context.Context,
	actorID string,
	commandName string,
	commandDigest string,
) (CommentCommandResult, bool, error) {
	idempotencyKey, err := scopedIdempotencyKey(ctx, actorID)
	if err != nil {
		return CommentCommandResult{}, false, err
	}
	result, found, err := s.data.Aggregate.FindReceipt(
		ctx,
		idempotencyKey,
		commandName,
		commandDigest,
	)
	if err != nil {
		return CommentCommandResult{}, false, unavailable(err)
	}
	if !found {
		return CommentCommandResult{}, false, nil
	}
	if result.Aggregate == nil {
		return CommentCommandResult{}, false, unavailable(errors.New("comment receipt has no aggregate"))
	}
	return commandResult(result.Aggregate, true), true, nil
}

func (s *CommentService) commit(
	ctx context.Context,
	actorID string,
	aggregate *commentmodel.Comment,
	expectedVersion int64,
	commandName string,
	commandDigest string,
	eventType string,
	eventPayload []byte,
	now time.Time,
) (CommentCommandResult, error) {
	idempotencyKey, err := scopedIdempotencyKey(ctx, actorID)
	if err != nil {
		return CommentCommandResult{}, err
	}
	eventID := eventIdentifier(idempotencyKey, eventType)
	result, err := s.data.Aggregate.Commit(ctx, commentports.Commit{
		Aggregate:        aggregate,
		ExpectedVersion:  expectedVersion,
		IdempotencyKey:   idempotencyKey,
		CommandName:      commandName,
		CommandDigest:    commandDigest,
		ReceiptExpiresAt: now.UTC().Add(commentReceiptTTL),
		Events: []commentports.OutboxEvent{{
			EventID:          eventID,
			EventType:        eventType,
			AggregateID:      aggregate.ID(),
			AggregateVersion: aggregate.Version(),
			Payload:          append([]byte(nil), eventPayload...),
			OccurredAt:       now.UTC(),
		}},
	})
	if err != nil {
		return CommentCommandResult{}, unavailable(err)
	}
	if result.Aggregate == nil {
		return CommentCommandResult{}, unavailable(errors.New("comment commit returned no aggregate"))
	}
	return commandResult(result.Aggregate, result.Replayed), nil
}

func (s *CommentService) recordIdempotentReceipt(
	ctx context.Context,
	actorID string,
	aggregate *commentmodel.Comment,
	commandName string,
	commandDigest string,
) (CommentCommandResult, error) {
	idempotencyKey, err := scopedIdempotencyKey(ctx, actorID)
	if err != nil {
		return CommentCommandResult{}, err
	}
	result, err := s.data.Aggregate.RecordIdempotentReceipt(
		ctx,
		commentports.IdempotentReceipt{
			Aggregate:        aggregate,
			IdempotencyKey:   idempotencyKey,
			CommandName:      commandName,
			CommandDigest:    commandDigest,
			ReceiptExpiresAt: s.now().UTC().Add(commentReceiptTTL),
		},
	)
	if err != nil {
		return CommentCommandResult{}, unavailable(err)
	}
	if result.Aggregate == nil {
		return CommentCommandResult{},
			unavailable(errors.New("comment no-op receipt returned no aggregate"))
	}
	return commandResult(result.Aggregate, result.Replayed), nil
}

func commandResult(aggregate *commentmodel.Comment, replayed bool) CommentCommandResult {
	return CommentCommandResult{
		ID:       aggregate.ID(),
		Version:  aggregate.Version(),
		Status:   aggregate.Status(),
		Replayed: replayed,
	}
}

func requiredActorID(raw string) (string, error) {
	actorID := strings.TrimSpace(raw)
	if actorID == "" {
		return "", contentgenerated.AppErrorFromUnauthorized(
			"comment command or private reader requires an authenticated persona actor",
		)
	}
	return actorID, nil
}

func scopedIdempotencyKey(ctx context.Context, actorID string) (string, error) {
	rawKey := strings.TrimSpace(commandmeta.IdempotencyKey(ctx))
	if rawKey == "" {
		return "", invalidArgument("comment command requires Idempotency-Key")
	}
	sum := sha256.Sum256([]byte(strings.TrimSpace(actorID) + "\x00" + rawKey))
	return "comment:" + hex.EncodeToString(sum[:]), nil
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

const commentReplyPreviewLimit = 1

// projectItems 组合 Comment、ContentReaction、MediaAsset 与 Post ownership 的
// 窄读投影。任何依赖读取失败都使 query fail closed，不产生默认零值伪成功。
func (s *CommentService) projectItems(
	ctx context.Context,
	readModels []commentmodel.ReadModel,
	actorID string,
	includeReplySummary bool,
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

	projectedByID := make(map[string]CommentListItem, len(allModels))
	for _, readModel := range allModels {
		projectedByID[readModel.ID] = projectCommentListItem(
			readModel,
			actorID,
			ownerships[readModel.PostID],
			reactionCounts[readModel.ID],
			viewerValues[readModel.ID],
			attachments,
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

func mapDomainError(err error) error {
	switch {
	case errors.Is(err, commentmodel.ErrDeleteForbidden):
		return contentgenerated.AppErrorFromCommentForbiddenDelete(err.Error())
	case errors.Is(err, commentmodel.ErrPinForbidden):
		return contentgenerated.AppErrorFromCommentPinForbidden(err.Error())
	case errors.Is(err, commentmodel.ErrPinInvalidTarget):
		return contentgenerated.AppErrorFromCommentPinInvalidTarget(err.Error())
	case errors.Is(err, commentmodel.ErrCommentDeleted):
		return contentgenerated.AppErrorFromCommentNotFound(err.Error())
	case errors.Is(err, commentmodel.ErrAttachmentForbidden):
		return contentgenerated.AppErrorFromCommentForbiddenDelete(err.Error())
	case errors.Is(err, commentmodel.ErrInvalidReplyTarget),
		errors.Is(err, commentmodel.ErrInvalidComment),
		errors.Is(err, commentmodel.ErrInvalidMutationClock):
		return invalidArgument(err.Error())
	default:
		return err
	}
}

func isCommentVersionConflict(err error) bool {
	var appError *rterr.AppError
	return errors.As(err, &appError) &&
		appError.Code.String() == contentgenerated.ErrVersionConflict.Error()
}

func commentNotFound(commentID string) error {
	return contentgenerated.AppErrorFromCommentNotFound(
		fmt.Sprintf("comment %s not found", strings.TrimSpace(commentID)),
	)
}

func invalidArgument(debug string) error {
	return contentgenerated.AppErrorFromInvalidArgument(debug)
}

func unavailable(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	return contentgenerated.AppErrorFromStorageWriteFailed(err.Error())
}

func unavailableRead(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	return contentgenerated.AppErrorFromStorageReadFailed(err.Error())
}

func createCommandDigest(command CreateCommentCommand) string {
	raw, _ := json.Marshal(command)
	return digestPayload("CreateComment", raw)
}

func deleteCommandDigest(command DeleteCommentCommand) string {
	raw, _ := json.Marshal(command)
	return digestPayload("DeleteComment", raw)
}

func pinCommandDigest(commandName string, command ChangeCommentPinCommand) string {
	raw, _ := json.Marshal(command)
	return digestPayload(commandName, raw)
}

func bindAttachmentsCommandDigest(command BindCommentAttachmentsCommand) string {
	raw, _ := json.Marshal(command)
	return digestPayload("BindCommentAttachments", raw)
}

func digestPayload(commandName string, payload []byte) string {
	h := sha256.New()
	_, _ = h.Write([]byte(commandName))
	_, _ = h.Write([]byte{0})
	_, _ = h.Write(payload)
	sum := h.Sum(nil)
	return hex.EncodeToString(sum[:])
}

func eventIdentifier(idempotencyKey, eventType string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(idempotencyKey) + ":" + eventType))
	return "evt_" + hex.EncodeToString(sum[:16])
}

func newIdentifier(prefix string) (string, error) {
	var raw [16]byte
	if _, err := rand.Read(raw[:]); err != nil {
		return "", err
	}
	return prefix + "_" + hex.EncodeToString(raw[:]), nil
}

func cloneStrings(values []string) []string {
	if len(values) == 0 {
		return []string{}
	}
	cloned := make([]string, 0, len(values))
	for _, value := range values {
		if value = strings.TrimSpace(value); value != "" {
			cloned = append(cloned, value)
		}
	}
	return cloned
}

func cloneMentions(values []commentmodel.Mention) []commentmodel.Mention {
	if len(values) == 0 {
		return []commentmodel.Mention{}
	}
	cloned := make([]commentmodel.Mention, len(values))
	copy(cloned, values)
	return cloned
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := value.UTC()
	return &cloned
}

func containsAssistantMention(mentions []commentmodel.Mention) bool {
	for _, mention := range mentions {
		if strings.EqualFold(strings.TrimSpace(mention.SubjectType), "assistant") {
			return true
		}
	}
	return false
}
