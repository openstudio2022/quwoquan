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

// reactionReceiptTTL 必须覆盖 72 小时命令接受窗口再留恢复余量，首期下限 96 小时。
// 低于它会让丢响应的命令在仍可重试的时间内失去可判定历史。
const reactionReceiptTTL = 96 * time.Hour

const (
	EventTypeContentReactionSet     = "ContentReactionSet"
	EventTypeContentReactionCleared = "ContentReactionCleared"
)

type Service struct {
	data       DataPorts
	now        func() time.Time
	basis      MutationBasisIssuer
	actorFence ActorLifecycleWriteFence
}

type ActorLifecycleWriteFence interface {
	MarkActorWriteOpen(context.Context, reactiondomain.Identity, time.Time) error
	ActorLifecycleClosed(context.Context, reactiondomain.Actor) (bool, error)
}

func NewService(data DataPorts, basis ...MutationBasisIssuer) *Service {
	if data.Aggregate == nil || data.State == nil || data.Target == nil || data.CommentCounts == nil {
		panic("ContentReaction Service requires aggregate store, state reader, target reader, and comment count reader")
	}
	service := &Service{data: data, now: time.Now}
	if len(basis) > 0 {
		service.basis = basis[0]
	}
	return service
}

func (s *Service) WithActorLifecycleWriteFence(fence ActorLifecycleWriteFence) *Service {
	if s != nil {
		s.actorFence = fence
	}
	return s
}

func (s *Service) LikePost(
	ctx context.Context,
	command LikePostCommand,
) (ContentReactionCommandResult, error) {
	identity, err := reactiondomain.NewPostIdentity(command.PostID, command.Actor)
	if err != nil {
		return ContentReactionCommandResult{}, invalidReactionCommand(err)
	}
	return s.mutate(ctx, "LikePost", identity, reactiondomain.ValueLike, command.Evidence, true)
}

func (s *Service) UnlikePost(
	ctx context.Context,
	command UnlikePostCommand,
) (ContentReactionCommandResult, error) {
	identity, err := reactiondomain.NewPostIdentity(command.PostID, command.Actor)
	if err != nil {
		return ContentReactionCommandResult{}, invalidReactionCommand(err)
	}
	return s.mutate(ctx, "UnlikePost", identity, reactiondomain.ValueNone, command.Evidence, true)
}

func (s *Service) ReactToComment(
	ctx context.Context,
	command ReactToCommentCommand,
) (CommentReactionCommandResult, error) {
	identity, err := reactiondomain.NewCommentIdentity(command.CommentID, command.Actor)
	if err != nil {
		return CommentReactionCommandResult{}, invalidReactionCommand(err)
	}
	result, err := s.mutate(ctx, "ReactToComment", identity, command.Reaction, command.Evidence, true)
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

func (s *Service) GetContentReactionPresentation(ctx context.Context, identity reactiondomain.Identity) (ContentReactionPresentationSlice, error) {
	if s.data.Statistics == nil {
		return ContentReactionPresentationSlice{}, reactionReadFailure(errors.New("reaction statistics reader unavailable"))
	}
	statistics, err := s.data.Statistics.ReadStatistics(ctx, identity.Target)
	if err != nil {
		return ContentReactionPresentationSlice{}, reactionReadFailure(err)
	}
	aggregate, found, err := s.data.Aggregate.Load(ctx, identity.AggregateID())
	if err != nil {
		return ContentReactionPresentationSlice{}, reactionReadFailure(err)
	}
	attachment := ContentReactionViewerAttachment{State: "attached"}
	value := reactiondomain.ValueNone
	version := int64(0)
	if found {
		value = aggregate.Value()
		version = aggregate.Version()
	}
	attachment.Reaction = &value
	attachment.Version = &version
	return ContentReactionPresentationSlice{Target: identity.Target, Statistics: statistics, ViewerAttachment: attachment}, nil
}

func (s *Service) GetContentReactionMutationBasis(ctx context.Context, query GetContentReactionMutationBasisQuery) (ContentReactionMutationBasisSlice, error) {
	if s.basis == nil {
		return ContentReactionMutationBasisSlice{}, reactionReadFailure(errors.New("reaction basis unavailable"))
	}
	target, err := s.data.Target.FindReactionTarget(ctx, query.Identity.Target)
	if err != nil {
		return ContentReactionMutationBasisSlice{}, reactionReadFailure(err)
	}
	if !target.Exists {
		return ContentReactionMutationBasisSlice{}, reactionerrors.AppErrorFromContentReactionTargetNotFound("target unavailable")
	}
	aggregate, found, err := s.data.Aggregate.Load(ctx, query.Identity.AggregateID())
	if err != nil {
		return ContentReactionMutationBasisSlice{}, reactionReadFailure(err)
	}
	version := int64(0)
	if found {
		version = aggregate.Version()
	}
	allowed := []reactiondomain.Value{reactiondomain.ValueNone, reactiondomain.ValueLike}
	if query.Identity.Target.Kind == reactiondomain.TargetKindComment {
		allowed = append(allowed, reactiondomain.ValueDislike)
	}
	basis, err := s.basis.Issue(MutationBasisClaims{Identity: query.Identity, ExpectedVersion: version, AllowedValues: allowed})
	if err != nil {
		return ContentReactionMutationBasisSlice{}, reactionReadFailure(err)
	}
	return ContentReactionMutationBasisSlice{TargetKind: string(query.Identity.Target.Kind), TargetID: query.Identity.Target.ID, MutationBasis: basis, ExpectedVersion: version}, nil
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
	if s.basis == nil {
		return ContentReactionStateSlice{}, reactionReadFailure(errors.New("reaction mutation basis signer unavailable"))
	}
	basis, err := s.basis.Issue(MutationBasisClaims{Identity: identity, ExpectedVersion: slice.Version, AllowedValues: []reactiondomain.Value{reactiondomain.ValueNone, reactiondomain.ValueLike}})
	if err != nil {
		return ContentReactionStateSlice{}, reactionReadFailure(err)
	}
	slice.MutationBasis = basis
	return slice, nil
}

func (s *Service) mutate(
	ctx context.Context,
	commandName string,
	identity reactiondomain.Identity,
	value reactiondomain.Value,
	evidence MutationEvidence,
	requireLiveTarget bool,
) (ContentReactionCommandResult, error) {
	idempotencyKey, err := requiredIdempotencyKey(ctx)
	if err != nil {
		return ContentReactionCommandResult{}, err
	}
	if s.basis == nil {
		return ContentReactionCommandResult{}, reactionWriteFailure(errors.New("reaction mutation basis signer unavailable"))
	}
	commandDigest, err := reactionCommandDigest(commandName, identity, value, evidence.ExpectedVersion, s.basis.Digest(evidence.MutationBasis))
	if err != nil {
		return ContentReactionCommandResult{}, reactionWriteFailure(err)
	}
	basisDigest := s.basis.Digest(evidence.MutationBasis)
	if replay, found, err := s.data.Aggregate.FindReceipt(ctx, identity, idempotencyKey, commandName, commandDigest, basisDigest); err != nil {
		return ContentReactionCommandResult{}, reactionWriteFailure(err)
	} else if found {
		if replay.Outcome != reactionports.ReceiptOutcomeCommitted {
			return ContentReactionCommandResult{}, contentgenerated.AppErrorFromIdempotencyConflict("reaction command was terminally finalized without execution")
		}
		return reactionResult(replay), nil
	}
	claims, err := s.basis.Verify(evidence.MutationBasis, identity, value, evidence.ExpectedVersion)
	if err != nil {
		return ContentReactionCommandResult{}, contentgenerated.AppErrorFromVersionConflict(err.Error())
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
	expectedVersion := evidence.ExpectedVersion
	// MongoDB BSON DateTime 以毫秒持久化。aggregate 与 outbox payload 在进入
	// 同一事务前就统一精度，避免读回后出现两个 occurredAt 真相。
	now := s.now().UTC().Truncate(time.Millisecond)
	var changed bool
	if !found {
		if expectedVersion != 0 {
			return ContentReactionCommandResult{}, contentgenerated.AppErrorFromVersionConflict("reaction expectedVersion changed")
		}
		aggregate, err = reactiondomain.New(identity, value, now)
		if err != nil {
			return ContentReactionCommandResult{}, invalidReactionCommand(err)
		}
		changed = value != reactiondomain.ValueNone
	} else {
		if aggregate.Version() != expectedVersion {
			return ContentReactionCommandResult{}, contentgenerated.AppErrorFromVersionConflict("reaction expectedVersion changed")
		}
		if aggregate.Identity() != identity {
			return ContentReactionCommandResult{},
				contentgenerated.AppErrorFromVersionConflict("reaction aggregate identity mismatch")
		}
		changed, err = aggregate.Set(value, now)
		if err != nil {
			return ContentReactionCommandResult{}, invalidReactionCommand(err)
		}
		if !changed {
			// 新接纳的无变化决定同样推进版本栅栏，并在存储层走真实 CAS；
			// 否则较旧的离线请求可以覆盖这次「保持不变」。
			if err := aggregate.AdvanceFence(now); err != nil {
				return ContentReactionCommandResult{}, invalidReactionCommand(err)
			}
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
	if changed && value != reactiondomain.ValueNone && s.actorFence != nil {
		if err := s.actorFence.MarkActorWriteOpen(ctx, identity, now); err != nil {
			return ContentReactionCommandResult{}, reactionWriteFailure(err)
		}
	}
	result, err := s.data.Aggregate.Commit(ctx, reactionports.Commit{
		Aggregate:       aggregate,
		ExpectedVersion: expectedVersion,
		IdempotencyKey:  idempotencyKey,
		CommandName:     commandName,
		CommandDigest:   commandDigest, BasisDigest: s.basis.Digest(evidence.MutationBasis), AcceptUntil: claims.AcceptUntil,
		ReceiptExpiresAt: now.Add(reactionReceiptTTL),
		Changed:          changed,
		Events:           events,
	})
	if err != nil {
		return ContentReactionCommandResult{}, reactionWriteFailure(err)
	}
	if changed && value != reactiondomain.ValueNone && s.actorFence != nil {
		closed, fenceErr := s.actorFence.ActorLifecycleClosed(ctx, identity.Actor)
		if fenceErr != nil {
			return ContentReactionCommandResult{}, reactionWriteFailure(fenceErr)
		}
		if closed {
			cleanupKey := fmt.Sprintf("actor-fence-converge:%s:m%d", identity.AggregateID(), result.Aggregate.Version())
			cleanupCtx := commandmeta.WithIdempotencyKey(ctx, cleanupKey)
			if _, cleanupErr := s.mutateInternal(cleanupCtx, "RemoveReactionForClosedActor", identity, reactiondomain.ValueNone, result.Aggregate.Version()); cleanupErr != nil {
				return ContentReactionCommandResult{}, cleanupErr
			}
			return ContentReactionCommandResult{}, contentgenerated.AppErrorFromVersionConflict("reaction actor lifecycle closed during commit")
		}
	}
	return reactionResult(result), nil
}

func (s *Service) RecoverCommand(ctx context.Context, command RecoverContentReactionCommand) (ContentReactionCommandRecoveryResult, error) {
	result, found, err := s.data.Aggregate.RecoverReceipt(ctx, command.Identity.Actor, command.IdempotencyKey, command.CommandName)
	if err != nil {
		return ContentReactionCommandRecoveryResult{}, reactionReadFailure(err)
	}
	if !found {
		return ContentReactionCommandRecoveryResult{IdempotencyKey: command.IdempotencyKey, Outcome: string(reactionports.ReceiptOutcomeHistoryUnavailable)}, nil
	}
	return contentRecoveryResult(command.IdempotencyKey, result), nil
}
func (s *Service) FinalizeExpiredCommand(ctx context.Context, command FinalizeExpiredContentReactionCommand) (ContentReactionCommandRecoveryResult, error) {
	if s.basis == nil {
		return ContentReactionCommandRecoveryResult{}, reactionWriteFailure(errors.New("reaction basis unavailable"))
	}
	claims, err := s.basis.VerifyForRecovery(command.Evidence.MutationBasis, command.Identity, command.Desired, command.Evidence.ExpectedVersion)
	if err != nil {
		return ContentReactionCommandRecoveryResult{}, contentgenerated.AppErrorFromVersionConflict(err.Error())
	}
	digest, err := reactionCommandDigest(command.CommandName, command.Identity, command.Desired, command.Evidence.ExpectedVersion, s.basis.Digest(command.Evidence.MutationBasis))
	if err != nil {
		return ContentReactionCommandRecoveryResult{}, err
	}
	result, err := s.data.Aggregate.FinalizeExpired(ctx, command.Identity, command.IdempotencyKey, command.CommandName, digest, s.basis.Digest(command.Evidence.MutationBasis), claims.AcceptUntil)
	if err != nil {
		return ContentReactionCommandRecoveryResult{}, reactionWriteFailure(err)
	}
	return contentRecoveryResult(command.IdempotencyKey, result), nil
}
func contentRecoveryResult(key string, result reactionports.CommitResult) ContentReactionCommandRecoveryResult {
	r := ContentReactionCommandRecoveryResult{IdempotencyKey: key, Outcome: string(result.Outcome), Replayed: result.Replayed}
	if result.Outcome == reactionports.ReceiptOutcomeCommitted && result.Aggregate != nil {
		v, c := result.Aggregate.Version(), result.Changed
		r.CommittedVersion = &v
		r.Changed = &c
	}
	return r
}

func (s *Service) removeForDeletedPost(ctx context.Context, identity reactiondomain.Identity) error {
	aggregate, found, err := s.data.Aggregate.Load(ctx, identity.AggregateID())
	if err != nil {
		return reactionReadFailure(err)
	}
	if !found {
		return nil
	}
	return s.removeForLifecycle(ctx, identity, aggregate.Version(), "PostDeleted")
}

func (s *Service) removeForLifecycle(ctx context.Context, identity reactiondomain.Identity, memberVersion int64, source string) error {
	commandName := "RemoveReactionFor" + strings.TrimSpace(source)
	_, err := s.mutateInternal(ctx, commandName, identity, reactiondomain.ValueNone, memberVersion)
	return err
}

// mutateInternal is the explicit owner-lifecycle authorization path. It never
// accepts a public mutation basis; its authority is the narrow cleanup port
// that supplies a verified lifecycle source and the member CAS version.
func (s *Service) mutateInternal(ctx context.Context, commandName string, identity reactiondomain.Identity, value reactiondomain.Value, expectedVersion int64) (ContentReactionCommandResult, error) {
	idempotencyKey, err := requiredIdempotencyKey(ctx)
	if err != nil {
		return ContentReactionCommandResult{}, err
	}
	commandDigest, err := reactionCommandDigest(commandName, identity, value, expectedVersion, "internal-lifecycle")
	if err != nil {
		return ContentReactionCommandResult{}, reactionWriteFailure(err)
	}
	if replay, found, err := s.data.Aggregate.FindReceipt(ctx, identity, idempotencyKey, commandName, commandDigest, "internal-lifecycle"); err != nil {
		return ContentReactionCommandResult{}, reactionWriteFailure(err)
	} else if found {
		return reactionResult(replay), nil
	}
	aggregate, found, err := s.data.Aggregate.Load(ctx, identity.AggregateID())
	if err != nil {
		return ContentReactionCommandResult{}, reactionReadFailure(err)
	}
	if !found {
		return ContentReactionCommandResult{}, nil
	}
	if aggregate.Version() != expectedVersion || aggregate.Identity() != identity {
		return ContentReactionCommandResult{}, contentgenerated.AppErrorFromVersionConflict("reaction lifecycle member version changed")
	}
	now := s.now().UTC().Truncate(time.Millisecond)
	changed, err := aggregate.Set(value, now)
	if err != nil {
		return ContentReactionCommandResult{}, invalidReactionCommand(err)
	}
	if !changed {
		return reactionResult(reactionports.CommitResult{Aggregate: aggregate, Outcome: reactionports.ReceiptOutcomeCommitted}), nil
	}
	events, err := reactionOutboxFacts(aggregate, true, idempotencyKey, "", now)
	if err != nil {
		return ContentReactionCommandResult{}, reactionWriteFailure(err)
	}
	result, err := s.data.Aggregate.Commit(ctx, reactionports.Commit{
		Aggregate: aggregate, ExpectedVersion: expectedVersion,
		IdempotencyKey: idempotencyKey, CommandName: commandName,
		CommandDigest: commandDigest, BasisDigest: "internal-lifecycle",
		AcceptUntil: now.Add(72 * time.Hour), ReceiptExpiresAt: now.Add(reactionReceiptTTL),
		Changed: true, Events: events,
	})
	if err != nil {
		return ContentReactionCommandResult{}, reactionWriteFailure(err)
	}
	return reactionResult(result), nil
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
	expectedVersion int64,
	basisDigest string,
) (string, error) {
	payload, err := json.Marshal(struct {
		Command         string `json:"command"`
		TargetKind      string `json:"targetKind"`
		TargetID        string `json:"targetId"`
		ActorDimension  string `json:"actorDimension"`
		ActorID         string `json:"actorId"`
		Reaction        string `json:"reaction"`
		ExpectedVersion int64  `json:"expectedVersion"`
		BasisDigest     string `json:"basisDigest"`
	}{
		Command:        commandName,
		TargetKind:     string(identity.Target.Kind),
		TargetID:       identity.Target.ID,
		ActorDimension: string(identity.Actor.Dimension),
		ActorID:        identity.Actor.ID,
		Reaction:       string(value), ExpectedVersion: expectedVersion, BasisDigest: basisDigest,
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
