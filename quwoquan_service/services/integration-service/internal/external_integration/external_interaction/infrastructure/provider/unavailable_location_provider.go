package provider

import (
	"context"
	"strings"

	"quwoquan_service/services/integration-service/generated/external_integration/location"
	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/model"
	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/ports"
)

// UnavailableLocationProvider 保留 disabled capability 的 HTTP 边界。
// capability 在 metadata 中被显式 blocked 时，服务本身仍可提供不依赖位置的
// operation；位置请求则以生成的结构化 RuntimeFailure 返回，禁止伪造外部凭据。
type UnavailableLocationProvider struct {
	reason string
}

func NewUnavailableLocationProvider(reason string) *UnavailableLocationProvider {
	return &UnavailableLocationProvider{reason: strings.TrimSpace(reason)}
}

func (p *UnavailableLocationProvider) Nearby(
	context.Context,
	model.NearbyQuery,
) ([]model.POI, error) {
	return nil, p.unavailableError()
}

func (p *UnavailableLocationProvider) Search(
	context.Context,
	model.SearchQuery,
) ([]model.POI, error) {
	return nil, p.unavailableError()
}

func (p *UnavailableLocationProvider) unavailableError() error {
	reason := p.reason
	if reason == "" {
		reason = "location lookup capability is unavailable"
	}
	return generated.AppErrorFromLocationProviderUnavailable(reason)
}

var _ ports.LocationProvider = (*UnavailableLocationProvider)(nil)
