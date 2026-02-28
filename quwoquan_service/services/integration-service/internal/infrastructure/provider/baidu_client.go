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

type BaiduClient struct {
	baseURL string
	ak      string
	client  *http.Client
}

func NewBaiduClient(baseURL, ak string, client *http.Client) *BaiduClient {
	if strings.TrimSpace(baseURL) == "" {
		baseURL = "https://api.map.baidu.com"
	}
	return &BaiduClient{
		baseURL: strings.TrimRight(baseURL, "/"),
		ak:      ak,
		client:  client,
	}
}

func (c *BaiduClient) Name() model.Provider { return model.ProviderBaidu }

func (c *BaiduClient) Nearby(ctx context.Context, q model.NearbyQuery) ([]model.POI, error) {
	if strings.TrimSpace(c.ak) == "" {
		return nil, fmt.Errorf("baidu ak is empty")
	}
	u, _ := url.Parse(c.baseURL + "/reverse_geocoding/v3/")
	values := u.Query()
	values.Set("ak", c.ak)
	values.Set("output", "json")
	values.Set("coordtype", "wgs84ll")
	values.Set("extensions_poi", "1")
	values.Set("radius", strconv.Itoa(q.RadiusMeters))
	values.Set("location", fmt.Sprintf("%f,%f", q.Lat, q.Lng))
	u.RawQuery = values.Encode()

	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	resp, err := c.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("baidu nearby status=%d", resp.StatusCode)
	}

	var out struct {
		Status int `json:"status"`
		Result struct {
			POIs []struct {
				UID      string `json:"uid"`
				Name     string `json:"name"`
				Addr     string `json:"addr"`
				Distance string `json:"distance"`
				Point    struct {
					Lat string `json:"y"`
					Lng string `json:"x"`
				} `json:"point"`
			} `json:"pois"`
		} `json:"result"`
		Message string `json:"message"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	if out.Status != 0 {
		return nil, fmt.Errorf("baidu nearby failed status=%d msg=%s", out.Status, out.Message)
	}

	items := make([]model.POI, 0, q.Limit)
	for _, poi := range out.Result.POIs {
		if len(items) >= q.Limit {
			break
		}
		lat, _ := strconv.ParseFloat(poi.Point.Lat, 64)
		lng, _ := strconv.ParseFloat(poi.Point.Lng, 64)
		distance, _ := strconv.Atoi(poi.Distance)
		items = append(items, model.POI{
			ID:             poi.UID,
			Provider:       model.ProviderBaidu,
			Name:           poi.Name,
			Address:        poi.Addr,
			Latitude:       lat,
			Longitude:      lng,
			DistanceMeters: distance,
		})
	}
	return items, nil
}

func (c *BaiduClient) Search(ctx context.Context, q model.SearchQuery) ([]model.POI, error) {
	if strings.TrimSpace(c.ak) == "" {
		return nil, fmt.Errorf("baidu ak is empty")
	}
	u, _ := url.Parse(c.baseURL + "/place/v2/search")
	values := u.Query()
	values.Set("ak", c.ak)
	values.Set("output", "json")
	values.Set("query", q.Query)
	values.Set("page_size", strconv.Itoa(q.Limit))
	if q.CityCode != "" {
		values.Set("region", q.CityCode)
	}
	if q.Lat != 0 || q.Lng != 0 {
		values.Set("location", fmt.Sprintf("%f,%f", q.Lat, q.Lng))
	}
	u.RawQuery = values.Encode()

	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	resp, err := c.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("baidu search status=%d", resp.StatusCode)
	}

	var out struct {
		Status  int `json:"status"`
		Results []struct {
			UID      string `json:"uid"`
			Name     string `json:"name"`
			Address  string `json:"address"`
			CityCode int    `json:"city_code"`
			Location struct {
				Lat float64 `json:"lat"`
				Lng float64 `json:"lng"`
			} `json:"location"`
		} `json:"results"`
		Message string `json:"message"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	if out.Status != 0 {
		return nil, fmt.Errorf("baidu search failed status=%d msg=%s", out.Status, out.Message)
	}

	items := make([]model.POI, 0, len(out.Results))
	for _, poi := range out.Results {
		items = append(items, model.POI{
			ID:        poi.UID,
			Provider:  model.ProviderBaidu,
			Name:      poi.Name,
			Address:   poi.Address,
			Latitude:  poi.Location.Lat,
			Longitude: poi.Location.Lng,
			CityCode:  strconv.Itoa(poi.CityCode),
		})
	}
	return items, nil
}
