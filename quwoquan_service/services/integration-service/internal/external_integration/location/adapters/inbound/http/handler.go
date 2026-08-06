package httpadapter

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	rerrors "quwoquan_service/runtime/errors"
	locationgenerated "quwoquan_service/services/integration-service/generated/external_integration/location"
	locationapplication "quwoquan_service/services/integration-service/internal/external_integration/location/application"
	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/model"
)

type Handler struct {
	service             *locationapplication.Service
	defaultNearbyRadius int
	defaultNearbyLimit  int
	defaultSearchLimit  int
	defaultLatitude     float64
	defaultLongitude    float64
}

func NewHandler(
	service *locationapplication.Service,
	defaultNearbyRadius int,
	defaultNearbyLimit int,
	defaultSearchLimit int,
	defaultLatitude float64,
	defaultLongitude float64,
) *Handler {
	return &Handler{
		service:             service,
		defaultNearbyRadius: defaultNearbyRadius,
		defaultNearbyLimit:  defaultNearbyLimit,
		defaultSearchLimit:  defaultSearchLimit,
		defaultLatitude:     defaultLatitude,
		defaultLongitude:    defaultLongitude,
	}
}

func (h *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	h.RegisterRoutes(mux)
	return mux
}

// RegisterRoutes 将 Location 的公开入口注册到调用方拥有的 mux；Location 不再
// 代替兄弟对象注册 ExternalInteraction 路由。
func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	mux.HandleFunc(locationgenerated.NearbyPath, h.handleNearby)
	mux.HandleFunc(locationgenerated.SearchPath, h.handleSearch)
	mux.HandleFunc(locationgenerated.RoutePath, h.handleRoute)
}

func (h *Handler) handleNearby(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		rerrors.WriteHTTPError(
			w,
			rerrors.NewInvalidArgument(rerrors.ModuleIntegration, "方法不支持", "only GET"),
			rerrors.HTTPWriteOptionsFromRequest(r),
		)
		return
	}

	lat := parseOptionalFloatWithFallback(
		r.URL.Query().Get(locationgenerated.QueryParamLat),
		h.defaultLatitude,
	)
	lng := parseOptionalFloatWithFallback(
		r.URL.Query().Get(locationgenerated.QueryParamLng),
		h.defaultLongitude,
	)

	radius := parsePositiveInt(r.URL.Query().Get(locationgenerated.QueryParamRadiusMeters), h.defaultNearbyRadius)
	limit := parsePositiveInt(r.URL.Query().Get(locationgenerated.QueryParamLimit), h.defaultNearbyLimit)
	items, serviceErr := h.service.Nearby(r.Context(), model.NearbyQuery{
		Lat:          lat,
		Lng:          lng,
		RadiusMeters: radius,
		Limit:        limit,
	})
	if serviceErr != nil {
		rerrors.WriteHTTPError(w, serviceErr, rerrors.HTTPWriteOptionsFromRequest(r))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{locationgenerated.ResponseListKey: poiToClientItems(items)})
}

func (h *Handler) handleSearch(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		rerrors.WriteHTTPError(
			w,
			rerrors.NewInvalidArgument(rerrors.ModuleIntegration, "方法不支持", "only GET"),
			rerrors.HTTPWriteOptionsFromRequest(r),
		)
		return
	}

	query := strings.TrimSpace(r.URL.Query().Get(locationgenerated.QueryParamQ))
	if query == "" {
		rerrors.WriteHTTPError(
			w,
			locationgenerated.AppErrorFromInvalidArgument("query parameter "+locationgenerated.QueryParamQ+" is empty"),
			rerrors.HTTPWriteOptionsFromRequest(r),
		)
		return
	}

	rawLat := r.URL.Query().Get(locationgenerated.QueryParamLat)
	rawLng := r.URL.Query().Get(locationgenerated.QueryParamLng)
	lat, latPresent := parseOptionalFloat(rawLat)
	lng, lngPresent := parseOptionalFloat(rawLng)
	if latPresent != lngPresent ||
		(strings.TrimSpace(rawLat) != "" && !latPresent) ||
		(strings.TrimSpace(rawLng) != "" && !lngPresent) ||
		(latPresent && (lat < -90 || lat > 90 || lng < -180 || lng > 180)) {
		rerrors.WriteHTTPError(
			w,
			locationgenerated.AppErrorFromInvalidArgument(
				"lat and lng must be a valid coordinate pair",
			),
			rerrors.HTTPWriteOptionsFromRequest(r),
		)
		return
	}
	limit := parsePositiveInt(r.URL.Query().Get(locationgenerated.QueryParamLimit), h.defaultSearchLimit)
	items, serviceErr := h.service.Search(r.Context(), model.SearchRequestFact{
		Query:     query,
		CityCode:  strings.TrimSpace(r.URL.Query().Get(locationgenerated.QueryParamCityCode)),
		Lat:       lat,
		Lng:       lng,
		HasCenter: latPresent,
		Limit:     limit,
	})
	if serviceErr != nil {
		rerrors.WriteHTTPError(w, serviceErr, rerrors.HTTPWriteOptionsFromRequest(r))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{locationgenerated.ResponseListKey: poiToClientItems(items)})
}

func (h *Handler) handleRoute(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		rerrors.WriteHTTPError(
			w,
			rerrors.NewInvalidArgument(
				rerrors.ModuleIntegration,
				"方法不支持",
				"only GET",
			),
			rerrors.HTTPWriteOptionsFromRequest(r),
		)
		return
	}
	query, parseErr := parseRouteQuery(r)
	if parseErr != nil {
		rerrors.WriteHTTPError(
			w,
			locationgenerated.AppErrorFromInvalidArgument(parseErr.Error()),
			rerrors.HTTPWriteOptionsFromRequest(r),
		)
		return
	}
	route, serviceErr := h.service.ReadRoute(r.Context(), query)
	if serviceErr != nil {
		rerrors.WriteHTTPError(
			w,
			serviceErr,
			rerrors.HTTPWriteOptionsFromRequest(r),
		)
		return
	}
	writeJSON(w, http.StatusOK, routeToClientItem(route))
}

func parseRouteQuery(r *http.Request) (model.RouteQuery, error) {
	originLat, err := parseRequiredFloat(
		r.URL.Query().Get(locationgenerated.QueryParamOriginLat),
		locationgenerated.QueryParamOriginLat,
	)
	if err != nil {
		return model.RouteQuery{}, err
	}
	originLng, err := parseRequiredFloat(
		r.URL.Query().Get(locationgenerated.QueryParamOriginLng),
		locationgenerated.QueryParamOriginLng,
	)
	if err != nil {
		return model.RouteQuery{}, err
	}
	destinationLat, err := parseRequiredFloat(
		r.URL.Query().Get(locationgenerated.QueryParamDestinationLat),
		locationgenerated.QueryParamDestinationLat,
	)
	if err != nil {
		return model.RouteQuery{}, err
	}
	destinationLng, err := parseRequiredFloat(
		r.URL.Query().Get(locationgenerated.QueryParamDestinationLng),
		locationgenerated.QueryParamDestinationLng,
	)
	if err != nil {
		return model.RouteQuery{}, err
	}
	if originLat < -90 || originLat > 90 ||
		destinationLat < -90 || destinationLat > 90 ||
		originLng < -180 || originLng > 180 ||
		destinationLng < -180 || destinationLng > 180 {
		return model.RouteQuery{}, rerrors.NewInvalidArgument(
			rerrors.ModuleIntegration,
			"路线坐标无效",
			"route coordinates are out of range",
		)
	}
	mode := model.TravelMode(
		strings.TrimSpace(
			r.URL.Query().Get(locationgenerated.QueryParamTravelMode),
		),
	)
	if mode == "" {
		mode = model.TravelModeDriving
	}
	switch mode {
	case model.TravelModeWalking,
		model.TravelModeCycling,
		model.TravelModeDriving:
	default:
		return model.RouteQuery{}, rerrors.NewInvalidArgument(
			rerrors.ModuleIntegration,
			"路线模式无效",
			"travelMode is not supported",
		)
	}
	return model.RouteQuery{
		OriginLat:      originLat,
		OriginLng:      originLng,
		DestinationLat: destinationLat,
		DestinationLng: destinationLng,
		TravelMode:     mode,
	}, nil
}

func parseRequiredFloat(raw string, parameter string) (float64, error) {
	value, ok := parseOptionalFloat(raw)
	if !ok {
		return 0, rerrors.NewInvalidArgument(
			rerrors.ModuleIntegration,
			"路线坐标无效",
			"query parameter "+parameter+" must be numeric",
		)
	}
	return value, nil
}

// poiToClientItems 按 integration/external_integration/location/projections/location_poi client_projection 输出，
// 不暴露 provider，与 LocationPoiDto 字段对齐。
func poiToClientItems(items []model.POI) []map[string]any {
	out := make([]map[string]any, len(items))
	for i, p := range items {
		m := map[string]any{
			locationgenerated.FieldKeyId:        p.ID,
			locationgenerated.FieldKeyName:      p.Name,
			locationgenerated.FieldKeyLatitude:  p.Latitude,
			locationgenerated.FieldKeyLongitude: p.Longitude,
		}
		if p.Address != "" {
			m[locationgenerated.FieldKeyAddress] = p.Address
		}
		if p.DistanceMeters > 0 {
			m[locationgenerated.FieldKeyDistanceMeters] = p.DistanceMeters
		}
		out[i] = m
	}
	return out
}

func routeToClientItem(route model.Route) map[string]any {
	return map[string]any{
		locationgenerated.FieldKeyRouteRef:             route.RouteRef,
		locationgenerated.FieldKeyOriginLatitude:       route.OriginLat,
		locationgenerated.FieldKeyOriginLongitude:      route.OriginLng,
		locationgenerated.FieldKeyDestinationLatitude:  route.DestinationLat,
		locationgenerated.FieldKeyDestinationLongitude: route.DestinationLng,
		locationgenerated.FieldKeyEncodedPolyline:      route.EncodedPolyline,
		locationgenerated.FieldKeyDurationSeconds:      route.DurationSeconds,
		locationgenerated.FieldKeyDistanceMeters:       route.DistanceMeters,
		locationgenerated.FieldKeyTravelMode:           route.TravelMode,
	}
}

func parseOptionalFloat(raw string) (float64, bool) {
	if strings.TrimSpace(raw) == "" {
		return 0, false
	}
	v, err := strconv.ParseFloat(strings.TrimSpace(raw), 64)
	if err != nil {
		return 0, false
	}
	return v, true
}

func parseOptionalFloatWithFallback(raw string, fallback float64) float64 {
	if v, ok := parseOptionalFloat(raw); ok {
		return v
	}
	return fallback
}

func parsePositiveInt(raw string, fallback int) int {
	v, err := strconv.Atoi(strings.TrimSpace(raw))
	if err != nil || v <= 0 {
		return fallback
	}
	return v
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}
