package templatesource

import (
	"context"
	"errors"
	"strings"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan/application"
	tripmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/model"
	templatemodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/model"
	templateports "quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/ports"
)

// StoreReader is the same-service typed read boundary used by the composed
// template-to-Trip command. It returns only the public, reusable template
// structure; members, stays, Moments, placements and Connector state are not
// represented by the source contract and therefore cannot be copied.
type StoreReader struct {
	store templateports.Store
}

func NewStoreReader(store templateports.Store) *StoreReader {
	return &StoreReader{store: store}
}

func (reader *StoreReader) GetOwnedActive(
	ctx context.Context,
	actorPersonaID string,
	templateID string,
) (application.TemplateSnapshot, error) {
	if reader == nil || reader.store == nil || strings.TrimSpace(actorPersonaID) == "" ||
		strings.TrimSpace(templateID) == "" {
		return application.TemplateSnapshot{}, tripmodel.ErrInvalidInput
	}
	template, err := reader.store.Get(ctx, strings.TrimSpace(templateID))
	if errors.Is(err, templateports.ErrNotFound) {
		return application.TemplateSnapshot{}, application.ErrTemplateNotFound
	}
	if err != nil {
		return application.TemplateSnapshot{}, application.ErrTemplateUnavailable
	}
	if strings.TrimSpace(template.OwnerPersonaID) != strings.TrimSpace(actorPersonaID) {
		return application.TemplateSnapshot{}, application.ErrTemplatePermissionDenied
	}
	if template.Status != templatemodel.StatusActive || template.Validate() != nil {
		return application.TemplateSnapshot{}, application.ErrTemplateUnavailable
	}
	items := make([]application.TemplateItem, 0, len(template.Items))
	for _, item := range template.Items {
		items = append(items, application.TemplateItem{
			TemplateItemID: item.TemplateItemID,
			DayOffset:      item.DayOffset,
			OrderInDay:     item.OrderInDay,
			Kind:           tripmodel.ItemKind(item.Kind),
			Title:          item.Title,
			PublicPlaceRef: toTripPlaceRef(item.PublicPlaceRef),
			Note:           item.Note,
		})
	}
	attributions := make([]tripmodel.SourceAttribution, 0, len(template.Attributions))
	for _, attribution := range template.Attributions {
		attributions = append(attributions, tripmodel.SourceAttribution{
			AttributionID:   attribution.AttributionID,
			Kind:            tripmodel.SourceAttributionKind(attribution.Kind),
			PostID:          attribution.ReferenceObjectID,
			AuthorPersonaID: attribution.AuthorPersonaID,
			Title:           attribution.Title,
		})
	}
	return application.TemplateSnapshot{
		TemplateID:     template.TemplateID,
		Version:        template.Version,
		OwnerPersonaID: template.OwnerPersonaID,
		Title:          template.Title,
		Items:          items,
		Attributions:   attributions,
	}, nil
}

func toTripPlaceRef(value *templatemodel.PlaceRef) *tripmodel.PlaceRef {
	if value == nil {
		return nil
	}
	return &tripmodel.PlaceRef{
		ObjectTypeRef: value.ObjectTypeRef,
		ObjectID:      value.ObjectID,
	}
}
