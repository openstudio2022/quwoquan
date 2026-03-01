package httpadapter

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	rerrors "quwoquan_service/runtime/errors"
	"quwoquan_service/services/integration-service/internal/application"
	"quwoquan_service/services/integration-service/internal/domain/location/model"
	"quwoquan_service/services/integration-service/internal/generated"
)

type Handler struct {
	service             *application.Service
	defaultNearbyRadius int
	defaultNearbyLimit  int
	defaultSearchLimit  int
	defaultLatitude     float64
	defaultLongitude    float64
}

func NewHandler(
	service *application.Service,
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
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	mux.HandleFunc(generated.NearbyPath, h.handleNearby)
	mux.HandleFunc(generated.SearchPath, h.handleSearch)
	return mux
}

func (h *Handler) handleNearby(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.NotFound(w, r)
		return
	}

	lat := parseOptionalFloatWithFallback(
		r.URL.Query().Get(generated.QueryParamLat),
		h.defaultLatitude,
	)
	lng := parseOptionalFloatWithFallback(
		r.URL.Query().Get(generated.QueryParamLng),
		h.defaultLongitude,
	)

	radius := parsePositiveInt(r.URL.Query().Get(generated.QueryParamRadiusMeters), h.defaultNearbyRadius)
	limit := parsePositiveInt(r.URL.Query().Get(generated.QueryParamLimit), h.defaultNearbyLimit)
	items, serviceErr := h.service.Nearby(r.Context(), model.NearbyQuery{
		Lat:          lat,
		Lng:          lng,
		RadiusMeters: radius,
		Limit:        limit,
	})
	if serviceErr != nil {
		rerrors.WriteHTTPError(w, serviceErr, rerrors.HTTPWriteOptions{})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{generated.ResponseListKey: poiToClientItems(items)})
}

func (h *Handler) handleSearch(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.NotFound(w, r)
		return
	}

	query := strings.TrimSpace(r.URL.Query().Get(generated.QueryParamQ))
	if query == "" {
		rerrors.WriteHTTPError(
			w,
			generated.AppErrorFromInvalidArgument("query parameter " + generated.QueryParamQ + " is empty"),
			rerrors.HTTPWriteOptions{},
		)
		return
	}

	lat, _ := parseOptionalFloat(r.URL.Query().Get(generated.QueryParamLat))
	lng, _ := parseOptionalFloat(r.URL.Query().Get(generated.QueryParamLng))
	limit := parsePositiveInt(r.URL.Query().Get(generated.QueryParamLimit), h.defaultSearchLimit)
	items, serviceErr := h.service.Search(r.Context(), model.SearchQuery{
		Query:    query,
		CityCode: strings.TrimSpace(r.URL.Query().Get(generated.QueryParamCityCode)),
		Lat:      lat,
		Lng:      lng,
		Limit:    limit,
	})
	if serviceErr != nil {
		rerrors.WriteHTTPError(w, serviceErr, rerrors.HTTPWriteOptions{})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{generated.ResponseListKey: poiToClientItems(items)})
}

// poiToClientItems 按 integration/location/projections/location_poi client_projection 输出，
// 不暴露 provider，与 LocationPoiDto 字段对齐。
func poiToClientItems(items []model.POI) []map[string]any {
	out := make([]map[string]any, len(items))
	for i, p := range items {
		m := map[string]any{
			generated.FieldKeyId:       p.ID,
			generated.FieldKeyName:     p.Name,
			generated.FieldKeyLatitude: p.Latitude,
			generated.FieldKeyLongitude: p.Longitude,
		}
		if p.Address != "" {
			m[generated.FieldKeyAddress] = p.Address
		}
		if p.DistanceMeters > 0 {
			m[generated.FieldKeyDistanceMeters] = p.DistanceMeters
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
