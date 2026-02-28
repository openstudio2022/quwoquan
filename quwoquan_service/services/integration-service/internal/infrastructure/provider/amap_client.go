package provider

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"

	"quwoquan_service/services/integration-service/internal/domain/location/model"
)

type AMapClient struct {
	baseURL string
	key     string
	client  *http.Client
}

func NewAMapClient(baseURL, key string, client *http.Client) *AMapClient {
	if strings.TrimSpace(baseURL) == "" {
		baseURL = "https://restapi.amap.com"
	}
	return &AMapClient{
		baseURL: strings.TrimRight(baseURL, "/"),
		key:     key,
		client:  client,
	}
}

func (c *AMapClient) Name() model.Provider { return model.ProviderAMap }

func (c *AMapClient) Nearby(ctx context.Context, q model.NearbyQuery) ([]model.POI, error) {
	if strings.TrimSpace(c.key) == "" {
		return nil, fmt.Errorf("amap key is empty")
	}
	u, _ := url.Parse(c.baseURL + "/v3/geocode/regeo")
	values := u.Query()
	values.Set("key", c.key)
	values.Set("location", fmt.Sprintf("%f,%f", q.Lng, q.Lat))
	values.Set("extensions", "all")
	values.Set("radius", strconv.Itoa(q.RadiusMeters))
	u.RawQuery = values.Encode()

	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	resp, err := c.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("amap nearby status=%d", resp.StatusCode)
	}

	var out struct {
		Status    string `json:"status"`
		Info      string `json:"info"`
		Regeocode struct {
			POIs []struct {
				ID       string `json:"id"`
				Name     string `json:"name"`
				Address  string `json:"address"`
				Distance string `json:"distance"`
				Location string `json:"location"`
				Adcode   string `json:"adcode"`
			} `json:"pois"`
		} `json:"regeocode"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	if out.Status != "1" {
		return nil, fmt.Errorf("amap nearby failed info=%s", out.Info)
	}

	items := make([]model.POI, 0, q.Limit)
	for _, poi := range out.Regeocode.POIs {
		if len(items) >= q.Limit {
			break
		}
		lat, lng := parseLngLat(poi.Location)
		distance, _ := strconv.Atoi(poi.Distance)
		items = append(items, model.POI{
			ID:             poi.ID,
			Provider:       model.ProviderAMap,
			Name:           poi.Name,
			Address:        poi.Address,
			Latitude:       lat,
			Longitude:      lng,
			DistanceMeters: distance,
			AdCode:         poi.Adcode,
		})
	}
	return items, nil
}

func (c *AMapClient) Search(ctx context.Context, q model.SearchQuery) ([]model.POI, error) {
	if strings.TrimSpace(c.key) == "" {
		return nil, fmt.Errorf("amap key is empty")
	}
	u, _ := url.Parse(c.baseURL + "/v3/place/text")
	values := u.Query()
	values.Set("key", c.key)
	values.Set("keywords", q.Query)
	values.Set("offset", strconv.Itoa(q.Limit))
	if q.CityCode != "" {
		values.Set("city", q.CityCode)
	}
	if q.Lat != 0 || q.Lng != 0 {
		values.Set("location", fmt.Sprintf("%f,%f", q.Lng, q.Lat))
	}
	u.RawQuery = values.Encode()

	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	resp, err := c.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("amap search status=%d", resp.StatusCode)
	}

	var out struct {
		Status string `json:"status"`
		Info   string `json:"info"`
		POIs   []struct {
			ID       string `json:"id"`
			Name     string `json:"name"`
			Address  string `json:"address"`
			Adcode   string `json:"adcode"`
			Citycode string `json:"citycode"`
			Location string `json:"location"`
		} `json:"pois"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	if out.Status != "1" {
		return nil, fmt.Errorf("amap search failed info=%s", out.Info)
	}

	items := make([]model.POI, 0, len(out.POIs))
	for _, poi := range out.POIs {
		lat, lng := parseLngLat(poi.Location)
		items = append(items, model.POI{
			ID:        poi.ID,
			Provider:  model.ProviderAMap,
			Name:      poi.Name,
			Address:   poi.Address,
			Latitude:  lat,
			Longitude: lng,
			CityCode:  poi.Citycode,
			AdCode:    poi.Adcode,
		})
	}
	return items, nil
}

func parseLngLat(raw string) (lat float64, lng float64) {
	parts := strings.Split(raw, ",")
	if len(parts) != 2 {
		return 0, 0
	}
	lng, _ = strconv.ParseFloat(parts[0], 64)
	lat, _ = strconv.ParseFloat(parts[1], 64)
	return lat, lng
}
