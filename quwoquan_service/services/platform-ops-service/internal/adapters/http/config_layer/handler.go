package config_layer

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	configapp "quwoquan_service/services/platform-ops-service/internal/application/platform_ops/config_layer"
	configmodel "quwoquan_service/services/platform-ops-service/internal/domain/platform_ops/config_layer/model"
	configports "quwoquan_service/services/platform-ops-service/internal/domain/platform_ops/config_layer/ports"
	platformgenerated "quwoquan_service/services/platform-ops-service/internal/generated"
)

type Handler struct {
	configs *configapp.Facade
}

type SetConfigLayerValueRequest struct {
	LayerID     string                  `json:"layerId"`
	ScopeLevel  string                  `json:"scopeLevel"`
	ScopeID     string                  `json:"scopeId"`
	Environment string                  `json:"environment,omitempty"`
	Cluster     string                  `json:"cluster,omitempty"`
	Service     string                  `json:"service,omitempty"`
	Value       configmodel.ConfigValue `json:"value"`
}

type ConfigLayerView struct {
	ID          string                    `json:"id"`
	Version     int64                     `json:"version"`
	ScopeLevel  string                    `json:"scopeLevel"`
	ScopeID     string                    `json:"scopeId"`
	Environment string                    `json:"environment,omitempty"`
	Cluster     string                    `json:"cluster,omitempty"`
	Service     string                    `json:"service,omitempty"`
	Entries     []configmodel.ConfigEntry `json:"entries"`
	Status      string                    `json:"status"`
	CreatedAt   string                    `json:"createdAt"`
	UpdatedAt   string                    `json:"updatedAt"`
}

type ConfigLayerSlice struct {
	Items []ConfigLayerView `json:"items"`
}

type ConfigKeyCatalogSlice struct {
	Items []configports.ConfigKeyDescriptor `json:"items"`
}

func NewHandler(configs *configapp.Facade) (*Handler, error) {
	if configs == nil {
		return nil, errors.New("config layer HTTP adapter requires facade")
	}
	return &Handler{configs: configs}, nil
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	switch {
	case r.Method == http.MethodGet && r.URL.Path == "/control-plane/platform/configs":
		h.listConfigKeys(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/control-plane/platform/configs/layers":
		h.listLayers(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/control-plane/platform/configs/resolve":
		h.resolve(w, r)
	case r.Method == http.MethodPost && strings.HasPrefix(r.URL.Path, "/control-plane/platform/configs/") && strings.HasSuffix(r.URL.Path, ":update"):
		h.setValue(w, r)
	default:
		writeError(w, r, platformgenerated.AppErrorFromConfigInvalid("config route or method is not registered"))
	}
}

func (h *Handler) listConfigKeys(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, ConfigKeyCatalogSlice{Items: h.configs.ListConfigKeys(r.Context())})
}

func (h *Handler) listLayers(w http.ResponseWriter, r *http.Request) {
	layers, err := h.configs.ListLayers(r.Context())
	if err != nil {
		writeError(w, r, platformgenerated.AppErrorFromConfigStorageReadFailed(err.Error()))
		return
	}
	items := make([]ConfigLayerView, 0, len(layers))
	for _, layer := range layers {
		items = append(items, toLayerView(layer))
	}
	writeJSON(w, http.StatusOK, ConfigLayerSlice{Items: items})
}

func (h *Handler) resolve(w http.ResponseWriter, r *http.Request) {
	result, err := h.configs.Resolve(r.Context(), configmodel.Scope{
		Environment: strings.TrimSpace(r.URL.Query().Get("env")),
		Cluster:     strings.TrimSpace(r.URL.Query().Get("cluster")),
		Service:     strings.TrimSpace(r.URL.Query().Get("service")),
	})
	if err != nil {
		if strings.Contains(err.Error(), "requires environment") {
			writeError(w, r, platformgenerated.AppErrorFromConfigInvalid(err.Error()))
			return
		}
		writeError(w, r, platformgenerated.AppErrorFromConfigStorageReadFailed(err.Error()))
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) setValue(w http.ResponseWriter, r *http.Request) {
	configKey := segmentBetween(r.URL.Path, "/control-plane/platform/configs/", ":update")
	if configKey == "" {
		writeError(w, r, platformgenerated.AppErrorFromConfigInvalid("configKey is required"))
		return
	}
	var request SetConfigLayerValueRequest
	if err := decodeStrictJSON(r, &request); err != nil {
		writeError(w, r, platformgenerated.AppErrorFromConfigInvalid(err.Error()))
		return
	}
	expectedVersion, err := parseIfMatchVersion(r.Header.Get("If-Match"))
	if err != nil {
		writeError(w, r, platformgenerated.AppErrorFromConfigInvalid(err.Error()))
		return
	}
	receipt, layer, err := h.configs.SetValue(r.Context(), configapp.SetValueCommand{
		LayerID: request.LayerID, ExpectedVersion: expectedVersion,
		Scope: configmodel.Scope{
			Level: request.ScopeLevel, ID: request.ScopeID, Environment: request.Environment,
			Cluster: request.Cluster, Service: request.Service,
		},
		ConfigKey: configKey, Value: request.Value,
		IdempotencyKey: strings.TrimSpace(r.Header.Get("Idempotency-Key")),
	})
	if err != nil {
		writeConfigError(w, r, err)
		return
	}
	response := struct {
		Layer   ConfigLayerView           `json:"layer"`
		Receipt configports.CommitReceipt `json:"receipt"`
	}{Layer: toLayerView(layer), Receipt: receipt}
	writeJSON(w, http.StatusOK, response)
}

func parseIfMatchVersion(raw string) (int64, error) {
	normalized := strings.TrimSpace(raw)
	normalized = strings.TrimPrefix(normalized, "W/")
	normalized = strings.Trim(normalized, "\"")
	version, err := strconv.ParseInt(normalized, 10, 64)
	if err != nil || version < 0 {
		return 0, fmt.Errorf("If-Match must contain a non-negative aggregate version")
	}
	return version, nil
}

func toLayerView(layer configmodel.ConfigLayer) ConfigLayerView {
	return ConfigLayerView{
		ID: layer.ID, Version: layer.Version, ScopeLevel: layer.Scope.Level, ScopeID: layer.Scope.ID,
		Environment: layer.Scope.Environment, Cluster: layer.Scope.Cluster, Service: layer.Scope.Service,
		Entries: layer.Entries, Status: layer.Status, CreatedAt: layer.CreatedAt, UpdatedAt: layer.UpdatedAt,
	}
}

func writeConfigError(w http.ResponseWriter, r *http.Request, err error) {
	switch {
	case errors.Is(err, configmodel.ErrNotFound):
		writeError(w, r, platformgenerated.AppErrorFromConfigLayerNotFound(err.Error()))
	case errors.Is(err, configmodel.ErrVersionConflict):
		writeError(w, r, platformgenerated.AppErrorFromConfigVersionConflict(err.Error()))
	case errors.Is(err, configmodel.ErrIdempotencyConflict):
		writeError(w, r, platformgenerated.AppErrorFromConfigIdempotencyConflict(err.Error()))
	case errors.Is(err, configmodel.ErrInvalid):
		writeError(w, r, platformgenerated.AppErrorFromConfigInvalid(err.Error()))
	default:
		writeError(w, r, platformgenerated.AppErrorFromConfigStorageWriteFailed(err.Error()))
	}
}

func decodeStrictJSON(r *http.Request, target any) error {
	decoder := json.NewDecoder(io.LimitReader(r.Body, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return fmt.Errorf("decode request: %w", err)
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return errors.New("request body must contain one JSON object")
	}
	return nil
}

func segmentBetween(path, prefix, suffix string) string {
	value := strings.TrimPrefix(path, prefix)
	value = strings.TrimSuffix(value, suffix)
	return strings.Trim(value, "/")
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}
