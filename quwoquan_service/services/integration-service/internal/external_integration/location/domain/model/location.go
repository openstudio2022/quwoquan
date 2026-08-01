package model

type POI struct {
	ID             string  `json:"id"`
	Name           string  `json:"name"`
	Address        string  `json:"address,omitempty"`
	Latitude       float64 `json:"latitude"`
	Longitude      float64 `json:"longitude"`
	DistanceMeters int     `json:"distanceMeters,omitempty"`
	CityCode       string  `json:"cityCode,omitempty"`
	AdCode         string  `json:"adCode,omitempty"`
}

type NearbyQuery struct {
	Lat          float64
	Lng          float64
	RadiusMeters int
	Limit        int
}

type SearchRequestFact struct {
	Query    string
	CityCode string
	Lat      float64
	Lng      float64
	Limit    int
}
