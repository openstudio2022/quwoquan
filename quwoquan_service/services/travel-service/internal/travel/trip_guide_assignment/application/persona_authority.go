package application

import (
	"context"
	"strings"

	"quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/domain/ports"
)

type PublicPersonaResolver interface {
	ValidatePublicGuidePersona(context.Context, string, string, model.Role) error
}
type PersonaAuthority struct{ resolver PublicPersonaResolver }

func NewPersonaAuthority(resolver PublicPersonaResolver) *PersonaAuthority {
	return &PersonaAuthority{resolver: resolver}
}
func (authority *PersonaAuthority) ValidateGuidePersona(ctx context.Context, assigneePersonaID, qualificationPersonaID string, role model.Role) error {
	if strings.TrimSpace(assigneePersonaID) == "" || !role.Valid() {
		return model.ErrInvalidArgument
	}
	if authority == nil || authority.resolver == nil {
		return ports.ErrReferenceUnavailable
	}
	return authority.resolver.ValidatePublicGuidePersona(ctx, strings.TrimSpace(assigneePersonaID), strings.TrimSpace(qualificationPersonaID), role)
}

var _ ports.PersonaAuthority = (*PersonaAuthority)(nil)
