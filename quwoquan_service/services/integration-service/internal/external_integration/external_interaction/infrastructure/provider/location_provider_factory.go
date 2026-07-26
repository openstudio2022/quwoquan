package provider

import (
	"fmt"
	"net/http"
	"net/url"
	"strings"

	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/providerbinding"
	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/ports"
)

const (
	LocationAdapterBaiduID           = "ext.map.baidu"
	LocationAdapterAMapID            = "ext.map.amap"
	LocationAdapterProtocolFixtureID = "ext.map.protocol_fixture"

	locationEndpointRoleBase = "base"
	locationBaiduAKSecret    = "INTEGRATION_LOCATION_BAIDU_AK"
	locationAMapKeySecret    = "INTEGRATION_LOCATION_AMAP_KEY"
	locationFixtureAKSecret  = "INTEGRATION_LOCATION_FIXTURE_AK"
)

// NewLocationProvider 仅为编译期选中的 Binding 装配一个具体 Adapter。
// 未登记的 Adapter 或缺少受控材料都在启动期失败，不尝试后备厂商。
func NewLocationProvider(
	binding providerbinding.ResolvedLocationBinding,
	client *http.Client,
) (ports.LocationProvider, error) {
	if client == nil {
		return nil, fmt.Errorf("location provider HTTP client is required")
	}
	if binding.AdapterID == LocationAdapterProtocolFixtureID {
		return NewProtocolFixtureLocationProvider(), nil
	}
	endpoint, err := requiredLocationBindingValue(
		binding.Endpoint,
		locationEndpointRoleBase,
		"endpoint",
	)
	if err != nil {
		return nil, err
	}
	if err := validateLocationProviderEndpoint(endpoint); err != nil {
		return nil, err
	}

	switch binding.AdapterID {
	case LocationAdapterBaiduID:
		accessKey, secretErr := requiredLocationBindingValue(
			binding.Secret,
			locationBaiduAKSecret,
			"secret",
		)
		if secretErr != nil {
			return nil, secretErr
		}
		return NewBaiduClient(endpoint, accessKey, client), nil
	case LocationAdapterAMapID:
		accessKey, secretErr := requiredLocationBindingValue(
			binding.Secret,
			locationAMapKeySecret,
			"secret",
		)
		if secretErr != nil {
			return nil, secretErr
		}
		return NewAMapClient(endpoint, accessKey, client), nil
	default:
		return nil, fmt.Errorf(
			"location provider adapter %q is not registered in this composition root",
			binding.AdapterID,
		)
	}
}

func requiredLocationBindingValue(
	lookup func(string) (string, bool),
	key string,
	kind string,
) (string, error) {
	value, ok := lookup(key)
	if !ok || strings.TrimSpace(value) == "" {
		return "", fmt.Errorf("location provider %s %q is required", kind, key)
	}
	return value, nil
}

func validateLocationProviderEndpoint(value string) error {
	endpoint, err := url.ParseRequestURI(value)
	if err != nil || endpoint.Scheme != "https" || endpoint.Host == "" {
		return fmt.Errorf("location provider endpoint must be an absolute HTTPS URL")
	}
	return nil
}
