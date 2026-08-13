package event

import (
	"context"
	"strings"
	"time"

	rtobs "quwoquan_service/runtime/observability"
	searchitemapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_search_item_view/application"
)

// 契约 runtime_entrypoints[].telemetry.metric 同名计数器（outcome=ok|error）。
var projectionOutcomes = rtobs.NewEntrypointOutcomeCounter("entity_homepage_search_item_projection")

type HomepagePublicEvent struct {
	EventType     string
	HomepageID    string
	EntityID      string
	DisplayName   string
	Summary       string
	EntityType    string
	Tags          []string
	City          string
	Address       string
	SourcePlaceID string
	RatingCount   int
	Latitude      *float64
	Longitude     *float64
	SourceVersion int64
	UpdatedAt     time.Time
}

type HomepageSearchItemViewProjector struct{ projector *searchitemapp.Projector }

func NewHandler(projector *searchitemapp.Projector) *HomepageSearchItemViewProjector {
	if projector == nil {
		panic("HomepageSearchItemView event handler requires projector")
	}
	return &HomepageSearchItemViewProjector{projector: projector}
}

func (h *HomepageSearchItemViewProjector) Apply(ctx context.Context, event HomepagePublicEvent) (applied bool, err error) {
	defer func() {
		outcome := "ok"
		if err != nil {
			outcome = "error"
		}
		projectionOutcomes.WithLabelValues(outcome).Inc()
	}()
	switch strings.TrimSpace(event.EventType) {
	case "HomepageRetired", "HomepageDeleted":
		return h.projector.Delete(ctx, event.HomepageID, event.SourceVersion)
	default:
		return h.projector.Upsert(ctx, searchitemapp.SearchItem{
			HomepageID: event.HomepageID, EntityID: event.EntityID,
			DisplayName: event.DisplayName, Summary: event.Summary, EntityType: event.EntityType,
			Tags: append([]string(nil), event.Tags...), City: event.City, Address: event.Address,
			SourcePlaceID: event.SourcePlaceID, RatingCount: event.RatingCount,
			Latitude: event.Latitude, Longitude: event.Longitude,
			SourceVersion: event.SourceVersion, UpdatedAt: event.UpdatedAt,
		})
	}
}
