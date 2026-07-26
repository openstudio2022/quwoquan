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
	MarkPendingBlockedBetween(ctx context.Context, subAccountA, subAccountB string) error
}

// PersonaRelationshipService is the only application facade for persona-to-
// persona follow and block commands. A caller cannot combine independent
// repositories and accidentally violate the aggregate rules.
type PersonaRelationshipService struct {
	store     relports.PersonaRelationshipStore
	personas  userrepo.PersonaReader
	cache     ProfileCacheInvalidator
	greetings GreetingBlockCascade
}

func NewPersonaRelationshipService(
	store relports.PersonaRelationshipStore,
	personas userrepo.PersonaReader,
	cache ProfileCacheInvalidator,
	greetings GreetingBlockCascade,
) *PersonaRelationshipService {
	if store == nil {
		panic("persona relationship store is required")
	}
	return &PersonaRelationshipService{
		store:     store,
		personas:  personas,
		cache:     cache,
		greetings: greetings,
	}
}

func (s *PersonaRelationshipService) Follow(
	ctx context.Context,
	sourcePersonaID, targetPersonaID, source, idempotencyKey string,
) (relmodel.MutationResult, error) {
	return s.execute(ctx, relmodel.Command{
		Kind:            relmodel.CommandFollow,
		SourcePersonaID: sourcePersonaID,
		TargetPersonaID: targetPersonaID,
		FollowSource:    source,
		IdempotencyKey:  idempotencyKey,
	})
}

func (s *PersonaRelationshipService) Unfollow(
	ctx context.Context,
	sourcePersonaID, targetPersonaID, idempotencyKey string,
) (relmodel.MutationResult, error) {
	return s.execute(ctx, relmodel.Command{
		Kind:            relmodel.CommandUnfollow,
		SourcePersonaID: sourcePersonaID,
		TargetPersonaID: targetPersonaID,
		IdempotencyKey:  idempotencyKey,
	})
}

func (s *PersonaRelationshipService) Block(
	ctx context.Context,
	sourcePersonaID, targetPersonaID, idempotencyKey string,
) (relmodel.MutationResult, error) {
	return s.execute(ctx, relmodel.Command{
		Kind:            relmodel.CommandBlock,
		SourcePersonaID: sourcePersonaID,
		TargetPersonaID: targetPersonaID,
		IdempotencyKey:  idempotencyKey,
	})
}

func (s *PersonaRelationshipService) Unblock(
	ctx context.Context,
	sourcePersonaID, targetPersonaID, idempotencyKey string,
) (relmodel.MutationResult, error) {
	return s.execute(ctx, relmodel.Command{
		Kind:            relmodel.CommandUnblock,
		SourcePersonaID: sourcePersonaID,
		TargetPersonaID: targetPersonaID,
		IdempotencyKey:  idempotencyKey,
	})
}

func (s *PersonaRelationshipService) execute(ctx context.Context, command relmodel.Command) (relmodel.MutationResult, error) {
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
	// Follow/Block 建立新语义边前必须证明 target 存在且未退役（404 掩蔽存在性）；
	// Unfollow/Unblock 是 unset 幂等清理，目标消失后仍允许收敛。
	if command.Kind == relmodel.CommandFollow || command.Kind == relmodel.CommandBlock {
		if err := s.ensureTargetPersonaFollowable(ctx, command.TargetPersonaID); err != nil {
			return relmodel.MutationResult{}, err
		}
	}
	result, err := s.store.Apply(ctx, command)
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
		return relmodel.MutationResult{}, err
	}
	if result.IdempotentReplay || !result.Changed {
		// A command which leaves the aggregate unchanged has the same externally
		// observable result as its original command. Treat it as an idempotent
		// response even when the caller did not supply an explicit request key.
		result.IdempotentReplay = true
		reltelemetry.Collector().RecordDuplicateCommand()
		return result, nil
	}

	s.invalidateProfileCaches(ctx, command.SourcePersonaID, command.TargetPersonaID)
	if command.Kind == relmodel.CommandBlock && s.greetings != nil {
		_ = s.greetings.MarkPendingBlockedBetween(ctx, command.SourcePersonaID, command.TargetPersonaID)
	}
	return result, nil
}

func invalidRelationshipArgument(debugMessage string) error {
	return relationshipgenerated.AppErrorFromRelationshipInvalidPair(debugMessage)
}

// ensureTargetPersonaFollowable 校验目标 persona 存在且未退役。
// personas reader 缺席（个别轻量测试装配）时跳过，由存储层兜底。
func (s *PersonaRelationshipService) ensureTargetPersonaFollowable(
	ctx context.Context,
	targetPersonaID string,
) error {
	if s.personas == nil {
		return nil
	}
	persona, err := s.personas.FindBySubAccountID(ctx, targetPersonaID)
	if err != nil {
		return err
	}
	if persona == nil || strings.EqualFold(strings.TrimSpace(persona.Status), "retired") {
		return relationshipgenerated.AppErrorFromRelationshipTargetNotFound(
			"target persona missing or retired",
		)
	}
	return nil
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

func (s *PersonaRelationshipService) ListFollowing(ctx context.Context, sourcePersonaID, cursor string, limit int) ([]relmodel.Direction, string, error) {
	return s.store.ListFollowing(ctx, strings.TrimSpace(sourcePersonaID), cursor, limit)
}

func (s *PersonaRelationshipService) ListFollowers(ctx context.Context, targetPersonaID, cursor string, limit int) ([]relmodel.Direction, string, error) {
	return s.store.ListFollowers(ctx, strings.TrimSpace(targetPersonaID), cursor, limit)
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
	persona, err := s.personas.FindBySubAccountID(ctx, personaID)
	if err != nil || persona == nil {
		return personaID
	}
	return persona.UserID
}
