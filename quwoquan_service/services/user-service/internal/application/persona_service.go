package application

import (
	"context"
	"fmt"
	"strings"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/services/user-service/internal/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/domain/user/ports"
)

type PersonaService struct {
	personas   PersonaStore
	activation userrepo.PersonaActivationStore
	pcache     ProfileCacheInvalidator
}

func NewPersonaService(
	personas PersonaStore,
	activation userrepo.PersonaActivationStore,
	pcache ProfileCacheInvalidator,
) *PersonaService {
	return &PersonaService{personas: personas, activation: activation, pcache: pcache}
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
		UserHandle:   subAccountID,
		Status:       "active",
	}
	if v, ok := data["displayName"].(string); ok {
		p.DisplayName = v
	}
	if v, ok := data["avatarUrl"].(string); ok {
		p.AvatarURL = strings.TrimSpace(v)
	}
	if v, ok := data["isPrivate"].(bool); ok {
		p.IsPrivate = v
	}
	normalizePersonaPersistence(p)
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
		nextAvatarURL := strings.TrimSpace(v)
		if nextAvatarURL != strings.TrimSpace(p.AvatarURL) {
			p.AvatarURL = nextAvatarURL
			if nextAvatarURL == "" {
				p.AvatarVersion = 0
			} else {
				p.AvatarVersion++
				if p.AvatarVersion <= 0 {
					p.AvatarVersion = 1
				}
			}
		}
	}
	if v, ok := data["isPrivate"].(bool); ok {
		p.IsPrivate = v
	}
	normalizePersonaPersistence(p)
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

	if err := s.activation.SwitchActive(ctx, p.UserID, p.SubAccountID); err != nil {
		return err
	}

	_ = s.pcache.Del(ctx, p.UserID)
	return nil
}
