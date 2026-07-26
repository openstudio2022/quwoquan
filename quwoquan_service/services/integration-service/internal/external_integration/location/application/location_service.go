package application

import (
	"context"
	"fmt"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/model"
	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/ports"
)

type Service struct {
	provider ports.LocationProvider
}

func NewService(provider ports.LocationProvider) (*Service, error) {
	if provider == nil {
		return nil, fmt.Errorf("location provider is required")
	}
	return &Service{
		provider: provider,
	}, nil
}

func (s *Service) Nearby(ctx context.Context, q model.NearbyQuery) (_ []model.POI, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "integration.Nearby",
		attribute.String("geo.lat", fmt.Sprintf("%g", q.Lat)),
		attribute.String("geo.lng", fmt.Sprintf("%g", q.Lng)))
	defer func() { rtobs.EndSpan(span, err) }()

	return s.provider.Nearby(ctx, q)
}

func (s *Service) Search(ctx context.Context, q model.SearchQuery) (_ []model.POI, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "integration.Search",
		attribute.String("search.query", q.Query),
		attribute.String("city.code", q.CityCode))
	defer func() { rtobs.EndSpan(span, err) }()

	return s.provider.Search(ctx, q)
}
