package provider

import (
	"fmt"
	"net/http"
	"net/url"
	"strings"

	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/ports"
	"quwoquan_service/services/integration-service/internal/external_integration/location/infrastructure/providerbinding"
)

const (
	LocationAdapterBaiduID           = "ext.map.baidu"
	LocationAdapterAMapID            = "ext.map.amap"
	LocationAdapterProtocolFixtureID = "ext.map.protocol_fixture"

	locationEndpointRoleBase = "base"
	locationBaiduAKSecret    = "INTEGRATION_LOCATION_BAIDU_AK"
	locationAMapKeySecret    = "INTEGRATION_LOCATION_AMAP_KEY"
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
	case LocationAdapterProtocolFixtureID:
		return NewBaiduClient(endpoint, "nonprod-protocol-substitute", client), nil
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

func NewPOISearchProvider(
	binding providerbinding.ResolvedLocationBinding,
	client *http.Client,
) (ports.POISearchProvider, error) {
	if binding.AdapterID != LocationAdapterNominatimID &&
		binding.AdapterID != LocationAdapterNominatimProtocolSubstituteID {
		return nil, fmt.Errorf(
			"POI search adapter %q is not registered in this composition root",
			binding.AdapterID,
		)
	}
	if !binding.ProbePassed {
		return nil, fmt.Errorf("POI search capability probe has not passed")
	}
	if err := validatePublicLocationBindingPolicy(binding); err != nil {
		return nil, err
	}
	endpoint, err := requiredLocationBindingValue(
		binding.Endpoint,
		locationEndpointRoleBase,
		"endpoint",
	)
	if err != nil {
		return nil, err
	}
	return newNominatimClient(
		binding.AdapterID,
		endpoint,
		client,
		RatePolicy{RequestsPerSecond: binding.RateLimitPerSecond},
	)
}

func NewRouteReadProvider(
	binding providerbinding.ResolvedLocationBinding,
	client *http.Client,
) (ports.RouteReadProvider, error) {
	if binding.AdapterID != LocationAdapterOSRMID &&
		binding.AdapterID != LocationAdapterOSRMProtocolSubstituteID {
		return nil, fmt.Errorf(
			"route read adapter %q is not registered in this composition root",
			binding.AdapterID,
		)
	}
	if !binding.ProbePassed {
		return nil, fmt.Errorf("route read capability probe has not passed")
	}
	if err := validatePublicLocationBindingPolicy(binding); err != nil {
		return nil, err
	}
	endpoint, err := requiredLocationBindingValue(
		binding.Endpoint,
		locationEndpointRoleBase,
		"endpoint",
	)
	if err != nil {
		return nil, err
	}
	return newOSRMClient(
		binding.AdapterID,
		endpoint,
		client,
		RatePolicy{RequestsPerSecond: binding.RateLimitPerSecond},
	)
}

func validatePublicLocationBindingPolicy(
	binding providerbinding.ResolvedLocationBinding,
) error {
	if strings.TrimSpace(binding.ConfigRef) == "" ||
		strings.TrimSpace(binding.RatePolicyRef) == "" ||
		binding.Timeout <= 0 ||
		binding.RateLimitPerSecond <= 0 {
		return fmt.Errorf("public location binding policy is incomplete")
	}
	return nil
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
	if err != nil || endpoint == nil || endpoint.Scheme != "https" ||
		endpoint.Host == "" {
		return fmt.Errorf("location provider endpoint must be an absolute HTTPS URL")
	}
	return nil
}
