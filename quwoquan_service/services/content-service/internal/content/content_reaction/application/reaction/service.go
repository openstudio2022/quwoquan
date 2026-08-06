package reaction

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/runtime/commandmeta"
	rterr "quwoquan_service/runtime/errors"
	reactionerrors "quwoquan_service/services/content-service/generated/content/content_reaction"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
)

const reactionReceiptTTL = 24 * time.Hour

const (
	EventTypeContentReactionSet     = "ContentReactionSet"
	EventTypeContentReactionCleared = "ContentReactionCleared"
)

type Service struct {
	data DataPorts
	now  func() time.Time
}

func NewService(data DataPorts) *Service {
	if data.Aggregate == nil || data.State == nil || data.Target == nil || data.CommentCounts == nil {
		panic("ContentReaction Service requires aggregate store, state reader, target reader, and comment count reader")
	}
	return &Service{
		data: data,
		now:  time.Now,
	}
}

func (s *Service) LikePost(
	ctx context.Context,
	command LikePostCommand,
) (ContentReactionCommandResult, error) {
	identity, err := reactiondomain.NewPostIdentity(command.PostID, command.Actor)
	if err != nil {
		return ContentReactionCommandResult{}, invalidReactionCommand(err)
	}
	return s.mutate(ctx, "LikePost", identity, reactiondomain.ValueLike, true)
}

func (s *Service) UnlikePost(
	ctx context.Context,
	command UnlikePostCommand,
) (ContentReactionCommandResult, error) {
	identity, err := reactiondomain.NewPostIdentity(command.PostID, command.Actor)
	if err != nil {
		return ContentReactionCommandResult{}, invalidReactionCommand(err)
	}
	return s.mutate(ctx, "UnlikePost", identity, reactiondomain.ValueNone, true)
}

func (s *Service) ReactToComment(
	ctx context.Context,
	command ReactToCommentCommand,
) (CommentReactionCommandResult, error) {
	identity, err := reactiondomain.NewCommentIdentity(command.CommentID, command.Actor)
	if err != nil {
		return CommentReactionCommandResult{}, invalidReactionCommand(err)
	}
	result, err := s.mutate(ctx, "ReactToComment", identity, command.Reaction, true)
	if err != nil {
		return CommentReactionCommandResult{}, err
	}
	likeCount, dislikeCount, err := s.data.CommentCounts.CountCommentReactions(
		ctx,
		identity.Target.ID,
	)
	if err != nil {
		return CommentReactionCommandResult{}, reactionReadFailure(err)
	}
	return CommentReactionCommandResult{
		ReactionID:   result.ReactionID,
		Version:      result.Version,
		Reaction:     result.Reaction,
		Changed:      result.Changed,
		Replayed:     result.Replayed,
		LikeCount:    likeCount,
		DislikeCount: dislikeCount,
	}, nil
}

func (s *Service) GetContentReactionState(
	ctx context.Context,
	query GetContentReactionStateQuery,
) (ContentReactionStateSlice, error) {
	identity, err := reactiondomain.NewPostIdentity(query.PostID, query.Actor)
	if err != nil {
		return ContentReactionStateSlice{}, invalidReactionCommand(err)
	}
	slice, err := s.data.State.ReadContentReactionState(ctx, identity)
	if err != nil {
		return ContentReactionStateSlice{}, reactionReadFailure(err)
	}
	return slice, nil
}

func (s *Service) mutate(
	ctx context.Context,
	commandName string,
	identity reactiondomain.Identity,
	value reactiondomain.Value,
	requireLiveTarget bool,
) (ContentReactionCommandResult, error) {
	idempotencyKey, err := requiredIdempotencyKey(ctx)
	if err != nil {
		return ContentReactionCommandResult{}, err
	}
	commandDigest, err := reactionCommandDigest(commandName, identity, value)
	if err != nil {
		return ContentReactionCommandResult{}, reactionWriteFailure(err)
	}
	if replay, found, err := s.data.Aggregate.FindReceipt(
		ctx,
		idempotencyKey,
		commandName,
		commandDigest,
	); err != nil {
		return ContentReactionCommandResult{}, reactionWriteFailure(err)
	} else if found {
		return reactionResult(replay), nil
	}
	targetAuthorID := ""
	if requireLiveTarget {
		targetSlice, err := s.data.Target.FindReactionTarget(ctx, identity.Target)
		if err != nil {
			return ContentReactionCommandResult{}, reactionReadFailure(err)
		}
		if !targetSlice.Exists {
			return ContentReactionCommandResult{},
				reactionerrors.AppErrorFromContentReactionTargetNotFound(
					"content reaction target does not exist",
				)
		}
		targetAuthorID = strings.TrimSpace(targetSlice.AuthorID)
	}

	aggregate, found, err := s.data.Aggregate.Load(ctx, identity.AggregateID())
	if err != nil {
		return ContentReactionCommandResult{}, reactionWriteFailure(err)
	}
	expectedVersion := int64(0)
	// MongoDB BSON DateTime 以毫秒持久化。aggregate 与 outbox payload 在进入
	// 同一事务前就统一精度，避免读回后出现两个 occurredAt 真相。
	now := s.now().UTC().Truncate(time.Millisecond)
	var changed bool
	if !found {
		aggregate, err = reactiondomain.New(identity, value, now)
		if err != nil {
			return ContentReactionCommandResult{}, invalidReactionCommand(err)
		}
		changed = value != reactiondomain.ValueNone
	} else {
		expectedVersion = aggregate.Version()
		if aggregate.Identity() != identity {
			return ContentReactionCommandResult{},
				contentgenerated.AppErrorFromVersionConflict("reaction aggregate identity mismatch")
		}
		changed, err = aggregate.Set(value, now)
		if err != nil {
			return ContentReactionCommandResult{}, invalidReactionCommand(err)
		}
	}

	events, err := reactionOutboxFacts(
		aggregate,
		changed,
		idempotencyKey,
		targetAuthorID,
		now,
	)
	if err != nil {
		return ContentReactionCommandResult{}, reactionWriteFailure(err)
	}
	result, err := s.data.Aggregate.Commit(ctx, reactionports.Commit{
		Aggregate:        aggregate,
		ExpectedVersion:  expectedVersion,
		IdempotencyKey:   idempotencyKey,
		CommandName:      commandName,
		CommandDigest:    commandDigest,
		ReceiptExpiresAt: now.Add(reactionReceiptTTL),
		Changed:          changed,
		Events:           events,
	})
	if err != nil {
		return ContentReactionCommandResult{}, reactionWriteFailure(err)
	}
	return reactionResult(result), nil
}

func (s *Service) removeForDeletedPost(
	ctx context.Context,
	identity reactiondomain.Identity,
) error {
	_, err := s.mutate(ctx, "RemoveReactionForDeletedPost", identity, reactiondomain.ValueNone, false)
	return err
}

func requiredIdempotencyKey(ctx context.Context) (string, error) {
	key := strings.TrimSpace(commandmeta.IdempotencyKey(ctx))
	if key == "" {
		return "", contentgenerated.AppErrorFromIdempotencyConflict(
			"content reaction command requires idempotency key",
		)
	}
	return key, nil
}

func reactionCommandDigest(
	commandName string,
	identity reactiondomain.Identity,
	value reactiondomain.Value,
) (string, error) {
	payload, err := json.Marshal(struct {
		Command        string `json:"command"`
		TargetKind     string `json:"targetKind"`
		TargetID       string `json:"targetId"`
		ActorDimension string `json:"actorDimension"`
		ActorID        string `json:"actorId"`
		Reaction       string `json:"reaction"`
	}{
		Command:        commandName,
		TargetKind:     string(identity.Target.Kind),
		TargetID:       identity.Target.ID,
		ActorDimension: string(identity.Actor.Dimension),
		ActorID:        identity.Actor.ID,
		Reaction:       string(value),
	})
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:]), nil
}

type reactionStateChangedFact struct {
	ReactionID     string    `json:"reactionId"`
	Version        int64     `json:"version"`
	TargetKind     string    `json:"targetKind"`
	TargetID       string    `json:"targetId"`
	TargetAuthorID string    `json:"targetAuthorId,omitempty"`
	ActorDimension string    `json:"actorDimension"`
	ActorID        string    `json:"actorId"`
	Reaction       string    `json:"reaction"`
	OccurredAt     time.Time `json:"occurredAt"`
	IdempotencyKey string    `json:"idempotencyKey"`
}

func reactionOutboxFacts(
	aggregate *reactiondomain.ContentReaction,
	changed bool,
	idempotencyKey string,
	targetAuthorID string,
	now time.Time,
) ([]reactionports.OutboxFact, error) {
	if !changed {
		return nil, nil
	}
	if aggregate == nil {
		return nil, errors.New("reaction aggregate is required for outbox")
	}
	snapshot := aggregate.Snapshot()
	eventType := EventTypeContentReactionCleared
	if snapshot.Value != reactiondomain.ValueNone {
		eventType = EventTypeContentReactionSet
		if strings.TrimSpace(targetAuthorID) == "" {
			return nil, errors.New("reaction set fact requires target author for notification recipients")
		}
	}
	payload, err := json.Marshal(reactionStateChangedFact{
		ReactionID:     snapshot.ID,
		Version:        snapshot.Version,
		TargetKind:     string(snapshot.Identity.Target.Kind),
		TargetID:       snapshot.Identity.Target.ID,
		TargetAuthorID: strings.TrimSpace(targetAuthorID),
		ActorDimension: string(snapshot.Identity.Actor.Dimension),
		ActorID:        snapshot.Identity.Actor.ID,
		Reaction:       string(snapshot.Value),
		OccurredAt:     now,
		IdempotencyKey: idempotencyKey,
	})
	if err != nil {
		return nil, err
	}
	return []reactionports.OutboxFact{{
		EventID:          fmt.Sprintf("reaction:%s:%d", snapshot.ID, snapshot.Version),
		EventType:        eventType,
		AggregateID:      snapshot.ID,
		AggregateVersion: snapshot.Version,
		Payload:          payload,
		OccurredAt:       now,
	}}, nil
}

func reactionResult(result reactionports.CommitResult) ContentReactionCommandResult {
	if result.Aggregate == nil {
		return ContentReactionCommandResult{}
	}
	return ContentReactionCommandResult{
		ReactionID: result.Aggregate.ID(),
		Version:    result.Aggregate.Version(),
		Reaction:   result.Aggregate.Value(),
		Liked:      result.Aggregate.IsLiked(),
		Changed:    result.Changed,
		Replayed:   result.Replayed,
	}
}

func invalidReactionCommand(err error) error {
	return contentgenerated.AppErrorFromInvalidArgument("content reaction command: " + err.Error())
}

func reactionWriteFailure(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	return contentgenerated.AppErrorFromStorageWriteFailed("content reaction write: " + err.Error())
}

func reactionReadFailure(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	return contentgenerated.AppErrorFromStorageReadFailed("content reaction read: " + err.Error())
}
