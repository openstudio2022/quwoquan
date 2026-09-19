package persona_relationship

import (
	"context"
	"errors"
	"strings"
	"time"

	relationshipgenerated "quwoquan_service/services/user-service/generated/relationship/persona_relationship"
	userrepo "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	relports "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/ports"
	reltelemetry "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/telemetry"
)

type ProfileCacheInvalidator interface {
	Del(ctx context.Context, userID string) error
}

type GreetingBlockCascade interface {
	MarkPendingBlockedBetween(ctx context.Context, personaA, personaB string) error
}

// PersonaRelationshipService is the only application facade for persona-to-
// persona follow and block commands. A caller cannot combine independent
// repositories and accidentally violate the aggregate rules.
type PersonaRelationshipService struct {
	store     relports.PersonaRelationshipStore
	personas  userrepo.PersonaReader
	cache     ProfileCacheInvalidator
	greetings GreetingBlockCascade
	targets   *RelationshipTargetResolver
	basis     MutationBasisIssuer
	receipts  CommandReceiptStore
}

// ServiceOption 只用于装配可选协作者；缺省装配保持普通 Persona 单轨。
type ServiceOption func(*PersonaRelationshipService)

// WithTargetResolver 接入唯一目标身份解析面，使普通 Persona 与已发布 Creator
// 共用同一 canonical 关系身份，并让 Creator 只能作为被关注方。
func WithTargetResolver(resolver *RelationshipTargetResolver) ServiceOption {
	return func(service *PersonaRelationshipService) {
		service.targets = resolver
	}
}

func WithMutationBasis(issuer MutationBasisIssuer, receipts CommandReceiptStore) ServiceOption {
	return func(service *PersonaRelationshipService) {
		service.basis = issuer
		service.receipts = receipts
		provider, hasSigner := issuer.(interface{ ReadCursorSigner() *ReadCursorSigner })
		consumer, acceptsSigner := service.store.(interface{ SetReadCursorSigner(*ReadCursorSigner) })
		if hasSigner && acceptsSigner {
			consumer.SetReadCursorSigner(provider.ReadCursorSigner())
		}
	}
}

type Facade interface {
	Follow(context.Context, string, string, string, CommandEvidence) (relmodel.MutationResult, error)
	Unfollow(context.Context, string, string, CommandEvidence) (relmodel.MutationResult, error)
	Block(context.Context, string, string, CommandEvidence) (relmodel.MutationResult, error)
	Unblock(context.Context, string, string, CommandEvidence) (relmodel.MutationResult, error)
	GetRelationship(context.Context, string, string) (relmodel.RelationshipState, error)
	GetRelationships(context.Context, string, []string) (map[string]relmodel.RelationshipState, error)
	CheckBlocked(context.Context, string, string) (bool, error)
	ListFollowing(context.Context, string, string, int, string, string) ([]relmodel.Direction, string, error)
	ListFollowers(context.Context, string, string, int, string, string) ([]relmodel.Direction, string, error)
	ListBlocked(context.Context, string, string, int) ([]relports.BlockedListItem, string, error)
	IssueMutationBasis(context.Context, string, string) (string, int64, string, error)
	RecoverCommand(context.Context, string, string, relmodel.CommandKind, string) (CommandRecoveryResult, error)
	FinalizeExpiredCommand(context.Context, string, string, relmodel.CommandKind, CommandEvidence) (CommandRecoveryResult, error)
}

var _ Facade = (*PersonaRelationshipService)(nil)

func NewPersonaRelationshipService(
	store relports.PersonaRelationshipStore,
	personas userrepo.PersonaReader,
	cache ProfileCacheInvalidator,
	greetings GreetingBlockCascade,
	options ...ServiceOption,
) *PersonaRelationshipService {
	if store == nil {
		panic("persona relationship store is required")
	}
	service := &PersonaRelationshipService{
		store:     store,
		personas:  personas,
		cache:     cache,
		greetings: greetings,
	}
	for _, option := range options {
		if option != nil {
			option(service)
		}
	}
	return service
}

func (s *PersonaRelationshipService) Follow(ctx context.Context, sourcePersonaID, targetPersonaID, source string, evidence CommandEvidence) (relmodel.MutationResult, error) {
	return s.execute(ctx, relmodel.Command{Kind: relmodel.CommandFollow, SourcePersonaID: sourcePersonaID, TargetPersonaID: targetPersonaID, FollowSource: source}, evidence)
}
func (s *PersonaRelationshipService) Unfollow(ctx context.Context, sourcePersonaID, targetPersonaID string, evidence CommandEvidence) (relmodel.MutationResult, error) {
	return s.execute(ctx, relmodel.Command{Kind: relmodel.CommandUnfollow, SourcePersonaID: sourcePersonaID, TargetPersonaID: targetPersonaID}, evidence)
}
func (s *PersonaRelationshipService) Block(ctx context.Context, sourcePersonaID, targetPersonaID string, evidence CommandEvidence) (relmodel.MutationResult, error) {
	return s.execute(ctx, relmodel.Command{Kind: relmodel.CommandBlock, SourcePersonaID: sourcePersonaID, TargetPersonaID: targetPersonaID}, evidence)
}
func (s *PersonaRelationshipService) Unblock(ctx context.Context, sourcePersonaID, targetPersonaID string, evidence CommandEvidence) (relmodel.MutationResult, error) {
	return s.execute(ctx, relmodel.Command{Kind: relmodel.CommandUnblock, SourcePersonaID: sourcePersonaID, TargetPersonaID: targetPersonaID}, evidence)
}

func (s *PersonaRelationshipService) execute(ctx context.Context, command relmodel.Command, evidence CommandEvidence) (relmodel.MutationResult, error) {
	startedAt := time.Now()
	defer func() { reltelemetry.Collector().RecordCommandLatency(time.Since(startedAt)) }()
	command.SourcePersonaID = strings.TrimSpace(command.SourcePersonaID)
	command.TargetPersonaID = strings.TrimSpace(command.TargetPersonaID)
	if command.SourcePersonaID == "" || command.TargetPersonaID == "" {
		return relmodel.MutationResult{}, invalidRelationshipArgument("sourcePersonaId and targetPersonaId required")
	}
	if command.SourcePersonaID == command.TargetPersonaID {
		return relmodel.MutationResult{}, invalidRelationshipArgument("persona cannot relate to itself")
	}
	// Follow/Block 建立新语义边前必须证明 target 是唯一 canonical 且当前可关注的
	// 公开身份（404 掩蔽存在性）；Unfollow/Unblock 是 unset 幂等清理，目标消失
	// 后仍允许收敛。
	if command.Kind == relmodel.CommandFollow || command.Kind == relmodel.CommandBlock {
		resolvedTarget, err := s.resolveCommandTarget(ctx, command.TargetPersonaID)
		if err != nil {
			return relmodel.MutationResult{}, err
		}
		command.TargetPersonaID = resolvedTarget
		if command.SourcePersonaID == command.TargetPersonaID {
			return relmodel.MutationResult{}, invalidRelationshipArgument("persona cannot relate to itself")
		}
	}
	if s.basis == nil {
		return relmodel.MutationResult{}, errors.New("relationship mutation basis signer unavailable")
	}
	pair, err := relmodel.NewPair(command.SourcePersonaID, command.TargetPersonaID)
	if err != nil {
		return relmodel.MutationResult{}, invalidRelationshipArgument(err.Error())
	}
	expectedVersion := evidence.ExpectedVersion
	command.IdempotencyKey = strings.TrimSpace(evidence.IdempotencyKey)
	command.MutationBasis = strings.TrimSpace(evidence.MutationBasis)
	command.ExpectedVersion = &expectedVersion
	claims, err := s.basis.Verify(command.MutationBasis, command, pair.ID)
	if err != nil {
		return relmodel.MutationResult{}, relationshipgenerated.AppErrorFromRelationshipCommandConflict(err.Error())
	}
	command.AcceptUntil = claims.AcceptUntil
	result, err := s.store.Apply(ctx, command)
	result.CanonicalTargetPersonaID = command.TargetPersonaID
	if err != nil {
		if errors.Is(err, relmodel.ErrFollowBlocked) {
			reltelemetry.Collector().RecordBlockRejection()
			return relmodel.MutationResult{}, relationshipgenerated.AppErrorFromRelationshipFollowBlocked(
				"persona relationship contains a block direction",
			)
		}
		if errors.Is(err, relmodel.ErrInvalidPersonaPair) {
			return relmodel.MutationResult{}, invalidRelationshipArgument(err.Error())
		}
		if errors.Is(err, relmodel.ErrIdempotencyKeyRequired) {
			return relmodel.MutationResult{}, relationshipgenerated.AppErrorFromRelationshipCommandKeyRequired(
				err.Error(),
			)
		}
		// 同键换命令、expectedVersion 过期与已终结命令都是需要读当前事实后由
		// 用户再决定的冲突，不是可静默重试的传输故障。
		if errors.Is(err, relmodel.ErrIdempotencyConflict) ||
			errors.Is(err, relmodel.ErrVersionConflict) ||
			errors.Is(err, relmodel.ErrCommandAlreadyFinalized) {
			return relmodel.MutationResult{}, relationshipgenerated.AppErrorFromRelationshipCommandConflict(
				err.Error(),
			)
		}
		// 摘要碰撞属于身份完整性失败：不能改写任何一对真实身份。
		if errors.Is(err, relmodel.ErrPairIdentityConflict) {
			return relmodel.MutationResult{}, invalidRelationshipArgument(err.Error())
		}
		if errors.Is(err, relmodel.ErrFollowingLimitExceeded) {
			return relmodel.MutationResult{}, relationshipgenerated.AppErrorFromRelationshipFollowingLimitExceeded(
				err.Error(),
			)
		}
		return relmodel.MutationResult{}, err
	}
	if result.IdempotentReplay {
		reltelemetry.Collector().RecordDuplicateCommand()
		return result, nil
	}
	if !result.Changed {
		return result, nil
	}

	s.invalidateProfileCaches(ctx, command.SourcePersonaID, command.TargetPersonaID)
	if command.Kind == relmodel.CommandBlock && s.greetings != nil {
		_ = s.greetings.MarkPendingBlockedBetween(ctx, command.SourcePersonaID, command.TargetPersonaID)
	}
	return result, nil
}

func (s *PersonaRelationshipService) IssueMutationBasis(ctx context.Context, actorPersonaID, targetIdentity string) (string, int64, string, error) {
	if s.basis == nil {
		return "", 0, "", errors.New("relationship mutation basis signer unavailable")
	}
	actorPersonaID = strings.TrimSpace(actorPersonaID)
	if s.targets != nil {
		resolvedActor, err := s.targets.ResolveActor(ctx, actorPersonaID)
		if err != nil {
			return "", 0, "", err
		}
		actorPersonaID = resolvedActor
	}
	resolvedTarget, err := s.resolveCommandTarget(ctx, targetIdentity)
	if err != nil {
		return "", 0, "", err
	}
	pair, err := relmodel.NewPair(actorPersonaID, resolvedTarget)
	if err != nil {
		return "", 0, "", invalidRelationshipArgument(err.Error())
	}
	state, err := s.store.Get(ctx, actorPersonaID, resolvedTarget)
	if err != nil {
		return "", 0, "", err
	}
	basis, err := s.basis.Issue(MutationBasisClaims{
		ActorPersonaID: actorPersonaID, TargetPersonaID: resolvedTarget,
		TargetKind: "persona", PairID: pair.ID, ExpectedVersion: state.Version,
		AllowedActions: []relmodel.CommandKind{relmodel.CommandFollow, relmodel.CommandUnfollow, relmodel.CommandBlock, relmodel.CommandUnblock},
	})
	return basis, state.Version, resolvedTarget, err
}

func (s *PersonaRelationshipService) RecoverCommand(ctx context.Context, actor, target string, operation relmodel.CommandKind, key string) (CommandRecoveryResult, error) {
	if s.receipts == nil {
		return CommandRecoveryResult{}, errors.New("relationship receipt store unavailable")
	}
	resolvedTarget, err := s.resolveCommandTargetForUnset(ctx, target)
	if err != nil {
		return CommandRecoveryResult{}, err
	}
	result, found, err := s.receipts.Recover(ctx, actor, key, operation, resolvedTarget)
	if err != nil {
		return CommandRecoveryResult{}, err
	}
	if !found {
		return CommandRecoveryResult{IdempotencyKey: key, Outcome: "history_unavailable"}, nil
	}
	return recoveryResult(key, result), nil
}

func (s *PersonaRelationshipService) FinalizeExpiredCommand(ctx context.Context, actor, target string, operation relmodel.CommandKind, evidence CommandEvidence) (CommandRecoveryResult, error) {
	if s.receipts == nil || s.basis == nil {
		return CommandRecoveryResult{}, errors.New("relationship command recovery unavailable")
	}
	resolvedTarget, err := s.resolveCommandTargetForUnset(ctx, target)
	if err != nil {
		return CommandRecoveryResult{}, err
	}
	pair, err := relmodel.NewPair(actor, resolvedTarget)
	if err != nil {
		return CommandRecoveryResult{}, err
	}
	expected := evidence.ExpectedVersion
	command := relmodel.Command{Kind: operation, SourcePersonaID: actor, TargetPersonaID: resolvedTarget, IdempotencyKey: evidence.IdempotencyKey, MutationBasis: evidence.MutationBasis, ExpectedVersion: &expected}
	claims, err := s.basis.VerifyForRecovery(command.MutationBasis, command, pair.ID)
	if err != nil {
		return CommandRecoveryResult{}, relationshipgenerated.AppErrorFromRelationshipCommandConflict(err.Error())
	}
	result, err := s.receipts.FinalizeExpired(ctx, actor, evidence.IdempotencyKey, operation, resolvedTarget, claims.AcceptUntil)
	if err != nil {
		return CommandRecoveryResult{}, err
	}
	return recoveryResult(evidence.IdempotencyKey, result), nil
}

func recoveryResult(key string, result relmodel.MutationResult) CommandRecoveryResult {
	recovery := CommandRecoveryResult{IdempotencyKey: key, Outcome: result.Outcome, Replayed: result.IdempotentReplay}
	if result.Outcome == relmodel.OutcomeCommitted {
		version, changed := result.State.Version, result.Changed
		recovery.CommittedVersion, recovery.Changed = &version, &changed
	}
	return recovery
}

func (s *PersonaRelationshipService) resolveCommandTargetForUnset(ctx context.Context, identity string) (string, error) {
	if s.targets != nil {
		resolved, err := s.targets.ResolveTarget(ctx, identity)
		if err == nil {
			return resolved.PersonaID, nil
		}
		// Unset/recovery must remain possible after target retirement. Immutable
		// canonical Persona IDs are accepted; aliases may not create a new Pair.
		if strings.HasPrefix(strings.TrimSpace(identity), "us_") {
			return strings.TrimSpace(identity), nil
		}
		return "", err
	}
	return strings.TrimSpace(identity), nil
}

func invalidRelationshipArgument(debugMessage string) error {
	return relationshipgenerated.AppErrorFromRelationshipInvalidPair(debugMessage)
}

// resolveCommandTarget 返回本次命令实际写入的 canonical 目标身份。
// 装配了 resolver 时由它统一裁决普通 Persona 与已发布 Creator；未装配时退回
// 只校验 Persona 存活，由存储层兜底 Pair 合法性。
func (s *PersonaRelationshipService) resolveCommandTarget(
	ctx context.Context,
	targetIdentity string,
) (string, error) {
	if s.targets != nil {
		resolved, err := s.targets.ResolveTarget(ctx, targetIdentity)
		if err != nil {
			return "", err
		}
		return resolved.PersonaID, nil
	}
	if s.personas == nil {
		return targetIdentity, nil
	}
	persona, err := s.personas.FindByPersonaID(ctx, targetIdentity)
	if err != nil {
		return "", err
	}
	if persona == nil || strings.EqualFold(strings.TrimSpace(persona.Status), "retired") {
		return "", relationshipgenerated.AppErrorFromRelationshipTargetNotFound(
			"target persona missing or retired",
		)
	}
	return targetIdentity, nil
}

func (s *PersonaRelationshipService) GetRelationship(
	ctx context.Context,
	viewerPersonaID, targetPersonaID string,
) (relmodel.RelationshipState, error) {
	viewerPersonaID = strings.TrimSpace(viewerPersonaID)
	targetPersonaID = strings.TrimSpace(targetPersonaID)
	if viewerPersonaID == "" || targetPersonaID == "" || viewerPersonaID == targetPersonaID {
		return relmodel.RelationshipState{}, nil
	}
	return s.store.Get(ctx, viewerPersonaID, targetPersonaID)
}

// GetRelationships 为一页列表一次性取回 viewer 与全部条目的关系快照。
// 列表组装必须用它替代逐条 GetRelationship/CheckBlocked，否则每页往返数会
// 随页大小线性增长。
func (s *PersonaRelationshipService) GetRelationships(
	ctx context.Context,
	viewerPersonaID string,
	targetPersonaIDs []string,
) (map[string]relmodel.RelationshipState, error) {
	return s.store.GetMany(ctx, strings.TrimSpace(viewerPersonaID), targetPersonaIDs)
}

func (s *PersonaRelationshipService) CheckBlocked(
	ctx context.Context,
	sourcePersonaID, targetPersonaID string,
) (bool, error) {
	state, err := s.GetRelationship(ctx, sourcePersonaID, targetPersonaID)
	if err != nil {
		return false, err
	}
	return state.IsBlocked, nil
}

func (s *PersonaRelationshipService) ListFollowing(ctx context.Context, sourcePersonaID, cursor string, limit int, viewerPersonaID, query string) ([]relmodel.Direction, string, error) {
	return s.store.ListFollowing(ctx, strings.TrimSpace(sourcePersonaID), cursor, limit, strings.TrimSpace(viewerPersonaID), strings.TrimSpace(query))
}

func (s *PersonaRelationshipService) ListFollowers(ctx context.Context, targetPersonaID, cursor string, limit int, viewerPersonaID, query string) ([]relmodel.Direction, string, error) {
	return s.store.ListFollowers(ctx, strings.TrimSpace(targetPersonaID), cursor, limit, strings.TrimSpace(viewerPersonaID), strings.TrimSpace(query))
}

func (s *PersonaRelationshipService) ListBlocked(
	ctx context.Context,
	sourcePersonaID, cursor string,
	limit int,
) ([]relports.BlockedListItem, string, error) {
	return s.store.ListBlocked(ctx, strings.TrimSpace(sourcePersonaID), cursor, limit)
}

func (s *PersonaRelationshipService) invalidateProfileCaches(ctx context.Context, personaIDs ...string) {
	if s.cache == nil {
		return
	}
	for _, personaID := range personaIDs {
		_ = s.cache.Del(ctx, personaID)
		ownerID := s.counterOwnerID(ctx, personaID)
		if ownerID != personaID {
			_ = s.cache.Del(ctx, ownerID)
		}
	}
}

func (s *PersonaRelationshipService) counterOwnerID(ctx context.Context, personaID string) string {
	personaID = strings.TrimSpace(personaID)
	if personaID == "" || s.personas == nil {
		return personaID
	}
	persona, err := s.personas.FindByPersonaID(ctx, personaID)
	if err != nil || persona == nil {
		return personaID
	}
	return persona.UserID
}
