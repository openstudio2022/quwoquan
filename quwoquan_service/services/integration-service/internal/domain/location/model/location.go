package model

import "context"

type Provider string

const (
	ProviderBaidu Provider = "baidu"
	ProviderAMap  Provider = "amap"
)

type POI struct {
	ID             string   `json:"id"`
	Provider       Provider `json:"provider"`
	Name           string   `json:"name"`
	Address        string   `json:"address,omitempty"`
	Latitude       float64  `json:"latitude"`
	Longitude      float64  `json:"longitude"`
	DistanceMeters int      `json:"distanceMeters,omitempty"`
	CityCode       string   `json:"cityCode,omitempty"`
	AdCode         string   `json:"adCode,omitempty"`
}

type NearbyQuery struct {
	Lat          float64
	Lng          float64
	RadiusMeters int
	Limit        int
}

type SearchQuery struct {
	Query    string
	CityCode string
	Lat      float64
	Lng      float64
	Limit    int
}

type ProviderClient interface {
	Name() Provider
	Nearby(ctx context.Context, q NearbyQuery) ([]POI, error)
	Search(ctx context.Context, q SearchQuery) ([]POI, error)
}
