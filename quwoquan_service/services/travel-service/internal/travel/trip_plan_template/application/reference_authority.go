package application

import (
	"context"
	"strings"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/ports"
)

type AttributionResolver interface {
	ValidatePublicAttribution(context.Context, string, model.Attribution) error
}

type ReferenceAuthority struct{ resolver AttributionResolver }

func NewReferenceAuthority(resolver AttributionResolver) *ReferenceAuthority {
	return &ReferenceAuthority{resolver: resolver}
}

func (authority *ReferenceAuthority) ValidateTemplateAttributions(ctx context.Context, actorPersonaID string, attributions []model.Attribution) error {
	if strings.TrimSpace(actorPersonaID) == "" {
		return model.ErrInvalidArgument
	}
	if len(attributions) == 0 {
		return nil
	}
	if authority == nil || authority.resolver == nil {
		return ports.ErrReferenceUnavailable
	}
	for _, attribution := range attributions {
		if err := authority.resolver.ValidatePublicAttribution(ctx, actorPersonaID, attribution); err != nil {
			return err
		}
	}
	return nil
}

var _ ports.ReferenceAuthority = (*ReferenceAuthority)(nil)
