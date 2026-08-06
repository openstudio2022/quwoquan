package model

type TravelMode string

const (
	TravelModeWalking TravelMode = "walking"
	TravelModeCycling TravelMode = "cycling"
	TravelModeDriving TravelMode = "driving"
)

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
	Query     string
	CityCode  string
	Lat       float64
	Lng       float64
	HasCenter bool
	Limit     int
}

type RouteQuery struct {
	OriginLat      float64
	OriginLng      float64
	DestinationLat float64
	DestinationLng float64
	TravelMode     TravelMode
}

type Route struct {
	RouteRef        string     `json:"routeRef"`
	OriginLat       float64    `json:"originLatitude"`
	OriginLng       float64    `json:"originLongitude"`
	DestinationLat  float64    `json:"destinationLatitude"`
	DestinationLng  float64    `json:"destinationLongitude"`
	EncodedPolyline string     `json:"encodedPolyline"`
	DurationSeconds int        `json:"durationSeconds"`
	DistanceMeters  int        `json:"distanceMeters"`
	TravelMode      TravelMode `json:"travelMode"`
}
