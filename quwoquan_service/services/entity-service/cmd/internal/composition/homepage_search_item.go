// Package composition wires public contracts between Entity objects without
// allowing either object's private implementation to become the other's truth
// source.
package composition

import (
	"context"
	"strings"

	homepageapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
	claimapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_claim_request/application"
	searchitemevent "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_search_item_view/adapters/inbound/event"
	searchitemapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_search_item_view/application"
)

type HomepageSearchItemProjection struct {
	handler *searchitemevent.Handler
}

func NewHomepageSearchItemProjection(index searchitemapp.Index) *HomepageSearchItemProjection {
	return &HomepageSearchItemProjection{
		handler: searchitemevent.NewHandler(searchitemapp.NewProjector(index)),
	}
}

func (a *HomepageSearchItemProjection) Project(
	ctx context.Context,
	event homepageapp.ProjectorEvent,
) error {
	version := event.SourceVersion
	if event.Homepage != nil && version <= 0 {
		version = event.Homepage.Version
	}
	if event.Homepage == nil || !homepageapp.HomepageSearchEligible(*event.Homepage) {
		_, err := a.handler.Apply(ctx, searchitemevent.HomepagePublicEvent{
			EventType: "HomepageRetired", HomepageID: event.HomepageID,
			SourceVersion: version,
		})
		return err
	}
	homepage := *event.Homepage
	projection := searchitemevent.HomepagePublicEvent{
		EventType: "HomepagePublished", HomepageID: homepage.ID,
		EntityID: homepage.CanonicalEntityID, DisplayName: homepage.Title,
		Summary: homepage.Subtitle, EntityType: homepage.HomepageType,
		Tags: append([]string(nil), homepage.CategoryTags...), City: homepage.City,
		Address: homepage.Address, SourcePlaceID: sourcePlaceAlias(homepage.LookupAliases),
		RatingCount: homepage.RatingCount, SourceVersion: version, UpdatedAt: homepage.UpdatedAt,
	}
	if homepage.Location != nil {
		latitude, longitude := homepage.Location.Latitude, homepage.Location.Longitude
		projection.Latitude, projection.Longitude = &latitude, &longitude
	}
	_, err := a.handler.Apply(ctx, projection)
	return err
}

func sourcePlaceAlias(aliases []string) string {
	const prefix = "place_"
	for _, raw := range aliases {
		value := strings.TrimSpace(raw)
		if len(value) != len(prefix)+16 || !strings.HasPrefix(value, prefix) {
			continue
		}
		valid := true
		for _, character := range value[len(prefix):] {
			if !((character >= '0' && character <= '9') ||
				(character >= 'a' && character <= 'f')) {
				valid = false
				break
			}
		}
		if valid {
			return value
		}
	}
	return ""
}

var _ homepageapp.Projector = (*HomepageSearchItemProjection)(nil)

type homepageClaimStateReader interface {
	FindHomepageClaimState(context.Context, string) (string, string, bool, error)
}

type HomepageClaimGate struct{ reader homepageClaimStateReader }

func NewHomepageClaimGate(reader homepageClaimStateReader) HomepageClaimGate {
	return HomepageClaimGate{reader: reader}
}

func (g HomepageClaimGate) FindHomepageState(
	ctx context.Context,
	homepageID string,
) (claimapp.HomepageState, bool, error) {
	status, claimStatus, found, err := g.reader.FindHomepageClaimState(ctx, homepageID)
	return claimapp.HomepageState{Status: status, ClaimStatus: claimStatus}, found, err
}

var _ claimapp.HomepageGate = HomepageClaimGate{}
