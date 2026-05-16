package application

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/services/user-service/internal/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/domain/user/repository"
	"quwoquan_service/services/user-service/internal/infrastructure/cache"
)

type PersonaService struct {
	personas userrepo.PersonaRepository
	pool     *pgxpool.Pool
	pcache   *cache.ProfileCache
}

func NewPersonaService(personas userrepo.PersonaRepository, pool *pgxpool.Pool, pcache *cache.ProfileCache) *PersonaService {
	return &PersonaService{personas: personas, pool: pool, pcache: pcache}
}

func (s *PersonaService) List(ctx context.Context, userID string) (_ []model.Persona, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.PersonaList",
		attribute.String("user.id", userID))
	defer func() { rtobs.EndSpan(span, err) }()

	return s.personas.FindByUserID(ctx, userID)
}

func (s *PersonaService) Create(ctx context.Context, userID string, data map[string]any) (_ *model.Persona, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.PersonaCreate",
		attribute.String("user.id", userID))
	defer func() { rtobs.EndSpan(span, err) }()

	subAccountID, err := buildSubAccountIdentity(extractOwnerRootPrefix(userID))
	if err != nil {
		return nil, err
	}
	p := &model.Persona{
		UserID:       userID,
		SubAccountID: subAccountID,
		Status:       "active",
	}
	if v, ok := data["displayName"].(string); ok {
		p.DisplayName = v
	}
	if v, ok := data["avatarUrl"].(string); ok {
		p.AvatarURL = v
	}
	if v, ok := data["isPrivate"].(bool); ok {
		p.IsPrivate = v
	}
	if err := s.personas.Create(ctx, p); err != nil {
		return nil, err
	}
	_ = s.pcache.Del(ctx, userID)
	return p, nil
}

func (s *PersonaService) Update(ctx context.Context, personaID string, data map[string]any) (_ *model.Persona, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.PersonaUpdate",
		attribute.String("persona.id", personaID))
	defer func() { rtobs.EndSpan(span, err) }()

	p, err := s.personas.FindByID(ctx, personaID)
	if err != nil {
		return nil, err
	}
	if p == nil {
		return nil, fmt.Errorf("persona not found: %s", personaID)
	}
	if v, ok := data["displayName"].(string); ok {
		p.DisplayName = v
	}
	if v, ok := data["avatarUrl"].(string); ok {
		p.AvatarURL = v
	}
	if v, ok := data["isPrivate"].(bool); ok {
		p.IsPrivate = v
	}
	if err := s.personas.Update(ctx, p); err != nil {
		return nil, err
	}
	_ = s.pcache.Del(ctx, p.UserID)
	return p, nil
}

func (s *PersonaService) Delete(ctx context.Context, personaID string) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.PersonaDelete",
		attribute.String("persona.id", personaID))
	defer func() { rtobs.EndSpan(span, err) }()

	p, err := s.personas.FindByID(ctx, personaID)
	if err != nil {
		return err
	}
	if p == nil {
		return fmt.Errorf("persona not found: %s", personaID)
	}
	if p.IsPrimary {
		return fmt.Errorf("cannot delete primary persona")
	}
	if err := s.personas.Delete(ctx, personaID); err != nil {
		return err
	}
	_ = s.pcache.Del(ctx, p.UserID)
	return nil
}

func (s *PersonaService) Activate(ctx context.Context, personaID string) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.PersonaActivate",
		attribute.String("persona.id", personaID))
	defer func() { rtobs.EndSpan(span, err) }()

	p, err := s.personas.FindByID(ctx, personaID)
	if err != nil {
		return err
	}
	if p == nil {
		return fmt.Errorf("persona not found: %s", personaID)
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	if _, err := tx.Exec(ctx,
		`UPDATE personas SET is_active = false, updated_at = NOW() WHERE user_id = $1 AND is_active = true`, p.UserID); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx,
		`UPDATE personas SET is_active = true, updated_at = NOW() WHERE sub_account_id = $1`, personaID); err != nil {
		return err
	}
	if err := tx.Commit(ctx); err != nil {
		return err
	}

	_ = s.pcache.Del(ctx, p.UserID)
	return nil
}
