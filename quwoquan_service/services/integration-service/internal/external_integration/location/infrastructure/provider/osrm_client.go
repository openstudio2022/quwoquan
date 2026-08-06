package provider

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"math"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/model"
	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/ports"
)

const (
	LocationAdapterOSRMID = "ext.route.osrm"
	routeReadCapabilityID = "location.route.read"
)

type OSRMClient struct {
	baseURL string
	client  *http.Client
	rate    *fixedWindowRateGate
}

func NewOSRMClient(
	baseURL string,
	client *http.Client,
	ratePolicy RatePolicy,
) (*OSRMClient, error) {
	if client == nil {
		return nil, fmt.Errorf("OSRM HTTP client is required")
	}
	if err := validateLocationProviderEndpoint(baseURL); err != nil {
		return nil, err
	}
	if ratePolicy.RequestsPerSecond <= 0 {
		return nil, fmt.Errorf("OSRM rate policy must be positive")
	}
	return &OSRMClient{
		baseURL: strings.TrimRight(strings.TrimSpace(baseURL), "/"),
		client:  client,
		rate:    newFixedWindowRateGate(ratePolicy),
	}, nil
}

func (c *OSRMClient) ReadRoute(
	ctx context.Context,
	query model.RouteQuery,
) (_ model.Route, err error) {
	startedAt := time.Now()
	defer func() {
		err = normalizeLocationProviderError(ctx, err)
		observePublicProvider(
			routeReadCapabilityID,
			LocationAdapterOSRMID,
			startedAt,
			err,
		)
	}()
	if !c.rate.allow() {
		return model.Route{}, ErrProviderRateLimited
	}
	profile, valid := osrmProfile(query.TravelMode)
	if !valid || !validCoordinate(query.OriginLat, query.OriginLng) ||
		!validCoordinate(query.DestinationLat, query.DestinationLng) {
		return model.Route{}, ErrProviderInvalidResponse
	}
	coordinates := formatOSRMCoordinate(query.OriginLng, query.OriginLat) + ";" +
		formatOSRMCoordinate(query.DestinationLng, query.DestinationLat)
	endpoint, parseErr := url.Parse(
		c.baseURL + "/route/v1/" + profile + "/" + coordinates,
	)
	if parseErr != nil {
		return model.Route{}, ErrProviderInvalidResponse
	}
	values := endpoint.Query()
	values.Set("overview", "full")
	values.Set("geometries", "polyline")
	values.Set("steps", "false")
	values.Set("alternatives", "false")
	endpoint.RawQuery = values.Encode()
	request, requestErr := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		endpoint.String(),
		nil,
	)
	if requestErr != nil {
		return model.Route{}, ErrProviderInvalidResponse
	}
	request.Header.Set("Accept", "application/json")
	request.Header.Set("User-Agent", "quwoquan-integration/1.0")
	response, requestErr := c.client.Do(request)
	if requestErr != nil {
		return model.Route{}, requestErr
	}
	defer response.Body.Close()
	switch {
	case response.StatusCode == http.StatusTooManyRequests:
		return model.Route{}, ErrProviderRateLimited
	case response.StatusCode < http.StatusOK ||
		response.StatusCode >= http.StatusMultipleChoices:
		return model.Route{}, errors.New("OSRM provider unavailable")
	}

	var payload osrmRouteResponseWire
	if decodeErr := decodeProviderJSON(response.Body, &payload); decodeErr != nil {
		return model.Route{}, ErrProviderInvalidResponse
	}
	if payload.Code != "Ok" || len(payload.Routes) == 0 {
		return model.Route{}, ErrProviderInvalidResponse
	}
	selected := payload.Routes[0]
	if strings.TrimSpace(selected.Geometry) == "" ||
		selected.Distance == nil || selected.Duration == nil ||
		*selected.Distance < 0 || *selected.Duration < 0 ||
		math.IsNaN(*selected.Distance) || math.IsInf(*selected.Distance, 0) ||
		math.IsNaN(*selected.Duration) || math.IsInf(*selected.Duration, 0) {
		return model.Route{}, ErrProviderPartialResponse
	}
	return model.Route{
		RouteRef:        routeReference(query, selected.Geometry),
		OriginLat:       query.OriginLat,
		OriginLng:       query.OriginLng,
		DestinationLat:  query.DestinationLat,
		DestinationLng:  query.DestinationLng,
		EncodedPolyline: selected.Geometry,
		DurationSeconds: int(math.Round(*selected.Duration)),
		DistanceMeters:  int(math.Round(*selected.Distance)),
		TravelMode:      query.TravelMode,
	}, nil
}

func osrmProfile(mode model.TravelMode) (string, bool) {
	switch mode {
	case model.TravelModeDriving:
		return "driving", true
	case model.TravelModeCycling:
		return "cycling", true
	case model.TravelModeWalking:
		return "walking", true
	default:
		return "", false
	}
}

func validCoordinate(latitude float64, longitude float64) bool {
	return !math.IsNaN(latitude) && !math.IsNaN(longitude) &&
		!math.IsInf(latitude, 0) && !math.IsInf(longitude, 0) &&
		latitude >= -90 && latitude <= 90 &&
		longitude >= -180 && longitude <= 180
}

func formatOSRMCoordinate(longitude float64, latitude float64) string {
	return strconv.FormatFloat(longitude, 'f', 6, 64) + "," +
		strconv.FormatFloat(latitude, 'f', 6, 64)
}

func routeReference(query model.RouteQuery, geometry string) string {
	sum := sha256.Sum256([]byte(strings.Join([]string{
		formatOSRMCoordinate(query.OriginLng, query.OriginLat),
		formatOSRMCoordinate(query.DestinationLng, query.DestinationLat),
		string(query.TravelMode),
		geometry,
	}, "|")))
	return "osrm:sha256:" + hex.EncodeToString(sum[:])
}

type osrmRouteResponseWire struct {
	Code   string          `json:"code"`
	Routes []osrmRouteWire `json:"routes"`
}

type osrmRouteWire struct {
	Geometry string   `json:"geometry"`
	Distance *float64 `json:"distance"`
	Duration *float64 `json:"duration"`
}

var _ ports.RouteReadProvider = (*OSRMClient)(nil)
