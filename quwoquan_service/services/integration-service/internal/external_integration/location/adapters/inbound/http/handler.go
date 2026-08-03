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

	lat, _ := parseOptionalFloat(r.URL.Query().Get(locationgenerated.QueryParamLat))
	lng, _ := parseOptionalFloat(r.URL.Query().Get(locationgenerated.QueryParamLng))
	limit := parsePositiveInt(r.URL.Query().Get(locationgenerated.QueryParamLimit), h.defaultSearchLimit)
	items, serviceErr := h.service.Search(r.Context(), model.SearchRequestFact{
		Query:    query,
		CityCode: strings.TrimSpace(r.URL.Query().Get(locationgenerated.QueryParamCityCode)),
		Lat:      lat,
		Lng:      lng,
		Limit:    limit,
	})
	if serviceErr != nil {
		rerrors.WriteHTTPError(w, serviceErr, rerrors.HTTPWriteOptionsFromRequest(r))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{locationgenerated.ResponseListKey: poiToClientItems(items)})
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
