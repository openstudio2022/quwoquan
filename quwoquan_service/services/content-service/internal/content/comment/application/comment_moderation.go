package comment

import (
	"context"
	"encoding/json"
	"strings"

	commenterrors "quwoquan_service/services/content-service/generated/content/comment"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	commentmodel "quwoquan_service/services/content-service/internal/content/comment/domain/model"
)

func (s *CommentService) HideComment(
	ctx context.Context,
	command HideCommentCommand,
) (CommentCommandResult, error) {
	return s.moderateComment(
		ctx,
		"HideComment",
		commentmodel.ModerationActionHide,
		command.CommentID,
		command.OperatorID,
		command.Reason,
	)
}

func (s *CommentService) RestoreComment(
	ctx context.Context,
	command RestoreCommentCommand,
) (CommentCommandResult, error) {
	return s.moderateComment(
		ctx,
		"RestoreComment",
		commentmodel.ModerationActionRestore,
		command.CommentID,
		command.OperatorID,
		command.Reason,
	)
}

func (s *CommentService) moderateComment(
	ctx context.Context,
	commandName string,
	action commentmodel.ModerationAction,
	commentID string,
	operatorID string,
	reason string,
) (CommentCommandResult, error) {
	operatorID, err := requiredCommentOperatorID(operatorID)
	if err != nil {
		return CommentCommandResult{}, err
	}
	commentID = strings.TrimSpace(commentID)
	reason = strings.TrimSpace(reason)
	commandDigest := moderationCommandDigest(
		commandName,
		commentID,
		operatorID,
		reason,
	)
	if replayed, found, replayErr := s.replay(
		ctx,
		operatorID,
		commandName,
		commandDigest,
	); replayErr != nil || found {
		return replayed, replayErr
	}

	for attempt := 0; attempt < 3; attempt++ {
		aggregate, found, loadErr := s.load(ctx, commentID)
		if loadErr != nil {
			return CommentCommandResult{}, loadErr
		}
		if !found {
			return CommentCommandResult{}, commentNotFound(commentID)
		}
		expectedVersion := aggregate.Version()
		now := s.now().UTC()
		var transitionErr error
		switch action {
		case commentmodel.ModerationActionHide:
			transitionErr = aggregate.Hide(operatorID, now)
		case commentmodel.ModerationActionRestore:
			transitionErr = aggregate.RestoreFromHidden(operatorID, now)
		default:
			return CommentCommandResult{},
				commenterrors.AppErrorFromCommentStatusTransitionInvalid(
					"unsupported Comment moderation action",
				)
		}
		if transitionErr != nil {
			return CommentCommandResult{}, mapDomainError(transitionErr)
		}
		snapshot := aggregate.Snapshot()
		payload, marshalErr := json.Marshal(commentModeratedEvent{
			CommentID:       snapshot.ID,
			Version:         snapshot.Version,
			PostID:          snapshot.PostID,
			ParentCommentID: snapshot.ParentCommentID,
			OperatorID:      operatorID,
			Action:          action,
			Reason:          reason,
			OccurredAt:      now,
		})
		if marshalErr != nil {
			return CommentCommandResult{}, unavailable(marshalErr)
		}
		result, commitErr := s.commit(
			ctx,
			operatorID,
			aggregate,
			expectedVersion,
			commandName,
			commandDigest,
			commentModeratedEventType,
			payload,
			now,
		)
		if commitErr == nil {
			return result, nil
		}
		if !isCommentVersionConflict(commitErr) || attempt == 2 {
			if isCommentVersionConflict(commitErr) {
				return CommentCommandResult{},
					contentgenerated.AppErrorFromVersionConflict(
						"comment changed repeatedly while applying moderation intent",
					)
			}
			return CommentCommandResult{}, commitErr
		}
	}
	panic("unreachable Comment moderation retry")
}

func requiredCommentOperatorID(raw string) (string, error) {
	operatorID := strings.TrimSpace(raw)
	if operatorID == "" {
		return "", commenterrors.AppErrorFromCommentModerationForbidden(
			"Comment moderation requires a verified operator account",
		)
	}
	return operatorID, nil
}

func moderationCommandDigest(
	commandName string,
	commentID string,
	operatorID string,
	reason string,
) string {
	raw, _ := json.Marshal(struct {
		CommentID  string `json:"commentId"`
		OperatorID string `json:"operatorId"`
		Reason     string `json:"reason"`
	}{
		CommentID:  commentID,
		OperatorID: operatorID,
		Reason:     reason,
	})
	return digestPayload(commandName, raw)
}
