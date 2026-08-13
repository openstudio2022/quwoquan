package provider

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/model"
	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/ports"
)

const (
	LocationAdapterNominatimID                   = "ext.map.nominatim"
	LocationAdapterNominatimProtocolSubstituteID = "ext.map.nominatim.protocol_substitute"
	poiSearchCapabilityID                        = "location.poi.search"
	maxProviderResponseBytes                     = 256 * 1024
)

type NominatimClient struct {
	baseURL string
	client  *http.Client
	rate    *fixedWindowRateGate
	adapter string
}

func NewNominatimClient(
	baseURL string,
	client *http.Client,
	ratePolicy RatePolicy,
) (*NominatimClient, error) {
	return newNominatimClient(
		LocationAdapterNominatimID,
		baseURL,
		client,
		ratePolicy,
	)
}

func newNominatimClient(
	adapterID string,
	baseURL string,
	client *http.Client,
	ratePolicy RatePolicy,
) (*NominatimClient, error) {
	if client == nil {
		return nil, fmt.Errorf("nominatim HTTP client is required")
	}
	if err := validateLocationProviderEndpoint(baseURL); err != nil {
		return nil, err
	}
	if ratePolicy.RequestsPerSecond <= 0 {
		return nil, fmt.Errorf("nominatim rate policy must be positive")
	}
	return &NominatimClient{
		baseURL: strings.TrimRight(strings.TrimSpace(baseURL), "/"),
		client:  client,
		rate:    newFixedWindowRateGate(ratePolicy),
		adapter: adapterID,
	}, nil
}

func (c *NominatimClient) Search(
	ctx context.Context,
	query model.SearchRequestFact,
) (_ []model.POI, err error) {
	startedAt := time.Now()
	defer func() {
		err = normalizeLocationProviderError(ctx, err)
		observePublicProvider(
			poiSearchCapabilityID,
			c.adapter,
			startedAt,
			err,
		)
	}()
	if !c.rate.allow() {
		return nil, ErrProviderRateLimited
	}
	if strings.TrimSpace(query.Query) == "" || query.Limit <= 0 {
		return nil, ErrProviderInvalidResponse
	}
	endpoint, parseErr := url.Parse(c.baseURL + "/search")
	if parseErr != nil {
		return nil, ErrProviderInvalidResponse
	}
	values := endpoint.Query()
	values.Set("q", query.Query)
	values.Set("format", "jsonv2")
	values.Set("addressdetails", "1")
	values.Set("limit", strconv.Itoa(query.Limit))
	if query.HasCenter || query.Lat != 0 || query.Lng != 0 {
		const halfWindowDegrees = 0.05
		values.Set("viewbox", strings.Join([]string{
			strconv.FormatFloat(query.Lng-halfWindowDegrees, 'f', 2, 64),
			strconv.FormatFloat(query.Lat+halfWindowDegrees, 'f', 2, 64),
			strconv.FormatFloat(query.Lng+halfWindowDegrees, 'f', 2, 64),
			strconv.FormatFloat(query.Lat-halfWindowDegrees, 'f', 2, 64),
		}, ","))
		values.Set("bounded", "0")
	}
	endpoint.RawQuery = values.Encode()

	request, requestErr := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		endpoint.String(),
		nil,
	)
	if requestErr != nil {
		return nil, ErrProviderInvalidResponse
	}
	request.Header.Set("Accept", "application/json")
	request.Header.Set("User-Agent", "quwoquan-integration/1.0")
	response, requestErr := c.client.Do(request)
	if requestErr != nil {
		return nil, requestErr
	}
	defer response.Body.Close()
	switch {
	case response.StatusCode == http.StatusTooManyRequests:
		return nil, ErrProviderRateLimited
	case response.StatusCode < http.StatusOK ||
		response.StatusCode >= http.StatusMultipleChoices:
		return nil, errors.New("nominatim provider unavailable")
	}

	var payload []nominatimPOIWire
	if decodeErr := decodeProviderJSON(response.Body, &payload); decodeErr != nil {
		return nil, ErrProviderInvalidResponse
	}
	items := make([]model.POI, 0, len(payload))
	for _, item := range payload {
		poi, mapErr := item.canonical()
		if mapErr != nil {
			return nil, ErrProviderPartialResponse
		}
		items = append(items, poi)
	}
	return items, nil
}

func decodeProviderJSON(body io.Reader, target any) error {
	decoder := json.NewDecoder(io.LimitReader(body, maxProviderResponseBytes))
	decoder.UseNumber()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return errors.New("provider response contains trailing JSON")
		}
		return err
	}
	return nil
}

type nominatimPOIWire struct {
	PlaceID     json.Number `json:"place_id"`
	OSMType     string      `json:"osm_type"`
	OSMID       json.Number `json:"osm_id"`
	Latitude    string      `json:"lat"`
	Longitude   string      `json:"lon"`
	Name        string      `json:"name"`
	DisplayName string      `json:"display_name"`
}

func (wire nominatimPOIWire) canonical() (model.POI, error) {
	latitude, latErr := strconv.ParseFloat(strings.TrimSpace(wire.Latitude), 64)
	longitude, lngErr := strconv.ParseFloat(strings.TrimSpace(wire.Longitude), 64)
	if latErr != nil || lngErr != nil || latitude < -90 || latitude > 90 ||
		longitude < -180 || longitude > 180 {
		return model.POI{}, ErrProviderPartialResponse
	}
	name := strings.TrimSpace(wire.Name)
	address := strings.TrimSpace(wire.DisplayName)
	if name == "" {
		name = firstDisplayNamePart(address)
	}
	if name == "" {
		return model.POI{}, ErrProviderPartialResponse
	}
	id := nominatimStableID(wire)
	if id == "" {
		return model.POI{}, ErrProviderPartialResponse
	}
	return model.POI{
		ID:        id,
		Name:      name,
		Address:   address,
		Latitude:  latitude,
		Longitude: longitude,
	}, nil
}

func nominatimStableID(wire nominatimPOIWire) string {
	osmType := strings.TrimSpace(wire.OSMType)
	osmID := strings.TrimSpace(wire.OSMID.String())
	if osmType != "" && osmID != "" {
		return "nominatim:" + osmType + ":" + osmID
	}
	placeID := strings.TrimSpace(wire.PlaceID.String())
	if placeID != "" {
		return "nominatim:place:" + placeID
	}
	return ""
}

func firstDisplayNamePart(displayName string) string {
	if index := strings.Index(displayName, ","); index >= 0 {
		return strings.TrimSpace(displayName[:index])
	}
	return strings.TrimSpace(displayName)
}

var _ ports.POISearchProvider = (*NominatimClient)(nil)
