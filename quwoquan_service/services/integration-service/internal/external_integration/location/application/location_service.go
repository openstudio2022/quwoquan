package application

import (
	"context"
	"fmt"
	"math"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/model"
	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/ports"
)

type Service struct {
	nearbyProvider ports.NearbyLocationProvider
	searchProvider ports.POISearchProvider
	routeProvider  ports.RouteReadProvider
}

func NewService(provider ports.LocationProvider) (*Service, error) {
	if provider == nil {
		return nil, fmt.Errorf("location provider is required")
	}
	return &Service{
		nearbyProvider: provider,
		searchProvider: provider,
	}, nil
}

func NewServiceWithProviders(
	nearbyProvider ports.NearbyLocationProvider,
	searchProvider ports.POISearchProvider,
	routeProvider ports.RouteReadProvider,
) (*Service, error) {
	if nearbyProvider == nil || searchProvider == nil || routeProvider == nil {
		return nil, fmt.Errorf("nearby, POI search and route providers are required")
	}
	return &Service{
		nearbyProvider: nearbyProvider,
		searchProvider: searchProvider,
		routeProvider:  routeProvider,
	}, nil
}

func (s *Service) Nearby(ctx context.Context, q model.NearbyQuery) (_ []model.POI, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "integration.Nearby",
		attribute.Bool("coarse_center.provided", q.Lat != 0 || q.Lng != 0),
		attribute.Int("result.limit", q.Limit))
	defer func() { rtobs.EndSpan(span, err) }()

	q.Lat = coarseCoordinate(q.Lat)
	q.Lng = coarseCoordinate(q.Lng)
	return s.nearbyProvider.Nearby(ctx, q)
}

func (s *Service) Search(ctx context.Context, q model.SearchRequestFact) (_ []model.POI, err error) {
	hasCenter := q.HasCenter || q.Lat != 0 || q.Lng != 0
	ctx, span := rtobs.StartBusinessSpan(ctx, "integration.Search",
		attribute.Int("search.query_length", len([]rune(q.Query))),
		attribute.Bool("coarse_center.provided", hasCenter),
		attribute.Bool("city_code.provided", q.CityCode != ""))
	defer func() { rtobs.EndSpan(span, err) }()

	if hasCenter {
		q.Lat = coarseCoordinate(q.Lat)
		q.Lng = coarseCoordinate(q.Lng)
		q.HasCenter = true
	}
	return s.searchProvider.Search(ctx, q)
}

func (s *Service) ReadRoute(ctx context.Context, q model.RouteQuery) (_ model.Route, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "integration.ReadRoute",
		attribute.String("travel.mode", string(q.TravelMode)))
	defer func() { rtobs.EndSpan(span, err) }()
	if s.routeProvider == nil {
		return model.Route{}, fmt.Errorf("route provider is unavailable")
	}
	return s.routeProvider.ReadRoute(ctx, q)
}

func coarseCoordinate(value float64) float64 {
	return math.Round(value*100) / 100
}
