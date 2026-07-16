package persona_relationship

import (
	"context"
	"errors"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	relmodel "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/model"
	relports "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/ports"
	reltelemetry "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/telemetry"
	userrepo "quwoquan_service/services/user-service/internal/domain/user/ports"
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
	profiles  userrepo.UserProfileStore
	personas  userrepo.PersonaReader
	cache     ProfileCacheInvalidator
	greetings GreetingBlockCascade
}

func NewPersonaRelationshipService(
	store relports.PersonaRelationshipStore,
	profiles userrepo.UserProfileStore,
	personas userrepo.PersonaReader,
	cache ProfileCacheInvalidator,
	greetings GreetingBlockCascade,
) *PersonaRelationshipService {
	if store == nil {
		panic("persona relationship store is required")
	}
	return &PersonaRelationshipService{
		store:     store,
		profiles:  profiles,
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
	result, err := s.store.Apply(ctx, command)
	if err != nil {
		if errors.Is(err, relmodel.ErrFollowBlocked) {
			reltelemetry.Collector().RecordBlockRejection()
			return relmodel.MutationResult{}, rterr.NewAppError(
				rterr.NewCode(rterr.ModuleUser, rterr.KindUser, "forbidden"),
				"当前关系不可关注",
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
	s.applyCounterEffects(ctx, command, result)
	if command.Kind == relmodel.CommandBlock && s.greetings != nil {
		_ = s.greetings.MarkPendingBlockedBetween(ctx, command.SourcePersonaID, command.TargetPersonaID)
	}
	return result, nil
}

func invalidRelationshipArgument(debugMessage string) error {
	return rterr.NewAppError(
		rterr.NewCode(rterr.ModuleUser, rterr.KindUser, "invalid_argument"),
		"关系主体无效",
		debugMessage,
	)
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

func (s *PersonaRelationshipService) ListBlocked(ctx context.Context, sourcePersonaID, cursor string, limit int) ([]relmodel.Direction, string, error) {
	return s.store.ListBlocked(ctx, strings.TrimSpace(sourcePersonaID), cursor, limit)
}

func (s *PersonaRelationshipService) applyCounterEffects(
	ctx context.Context,
	command relmodel.Command,
	result relmodel.MutationResult,
) {
	switch command.Kind {
	case relmodel.CommandFollow:
		s.incrementCounters(ctx, command.TargetPersonaID, command.SourcePersonaID, 1)
	case relmodel.CommandUnfollow:
		s.incrementCounters(ctx, command.TargetPersonaID, command.SourcePersonaID, -1)
	case relmodel.CommandBlock:
		for _, direction := range result.ClearedFollowing {
			s.incrementCounters(ctx, direction.TargetPersonaID, direction.SourcePersonaID, -1)
		}
	}
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

func (s *PersonaRelationshipService) incrementCounters(ctx context.Context, targetPersonaID, sourcePersonaID string, delta int64) {
	if s.profiles == nil {
		return
	}
	targetOwnerID := s.counterOwnerID(ctx, targetPersonaID)
	sourceOwnerID := s.counterOwnerID(ctx, sourcePersonaID)
	if err := s.profiles.IncrementCounter(ctx, targetOwnerID, "follower_count", delta); err != nil {
		reltelemetry.Collector().RecordCounterMismatch()
	}
	if err := s.profiles.IncrementCounter(ctx, sourceOwnerID, "following_count", delta); err != nil {
		reltelemetry.Collector().RecordCounterMismatch()
	}
	s.reconcileCounter(ctx, targetOwnerID, "follower_count")
	s.reconcileCounter(ctx, sourceOwnerID, "following_count")
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

func (s *PersonaRelationshipService) reconcileCounter(ctx context.Context, ownerID, field string) {
	if s.profiles == nil || strings.TrimSpace(ownerID) == "" {
		return
	}
	profile, err := s.profiles.FindByID(ctx, ownerID)
	if err != nil || profile == nil {
		return
	}
	expected, err := s.expectedCounterValue(ctx, ownerID, field)
	if err != nil {
		return
	}
	current := profile.FollowerCount
	if field == "following_count" {
		current = profile.FollowingCount
	}
	if current == expected {
		return
	}
	reltelemetry.Collector().RecordCounterMismatch()
	if err := s.profiles.IncrementCounter(ctx, ownerID, field, expected-current); err != nil {
		reltelemetry.Collector().RecordCounterMismatch()
	}
}

func (s *PersonaRelationshipService) expectedCounterValue(ctx context.Context, ownerID, field string) (int64, error) {
	personaIDs := []string{ownerID}
	if s.personas != nil {
		personas, err := s.personas.FindByUserID(ctx, ownerID)
		if err != nil {
			return 0, err
		}
		personaIDs = personaIDs[:0]
		for _, persona := range personas {
			if persona.SubAccountID == "" || strings.EqualFold(persona.Status, "retired") {
				continue
			}
			personaIDs = append(personaIDs, persona.SubAccountID)
		}
		if len(personaIDs) == 0 {
			personaIDs = []string{ownerID}
		}
	}
	var total int64
	for _, personaID := range personaIDs {
		var (
			value int64
			err   error
		)
		if field == "follower_count" {
			value, err = s.store.CountFollowers(ctx, personaID)
		} else {
			value, err = s.store.CountFollowing(ctx, personaID)
		}
		if err != nil {
			return 0, err
		}
		total += value
	}
	return total, nil
}
