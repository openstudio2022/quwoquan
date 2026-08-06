package config_layer

import (
	"errors"
	"net/http"

	platformgenerated "quwoquan_service/control-plane/platform-ops/generated/platform_ops/config_snapshot"
	configapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_snapshot/application/config_layer"
)

type TopologyHandler struct {
	facade *configapp.TopologyFacade
}

func NewTopologyHandler(facade *configapp.TopologyFacade) (*TopologyHandler, error) {
	if facade == nil {
		return nil, errors.New("config snapshot topology HTTP adapter requires facade")
	}
	return &TopologyHandler{facade: facade}, nil
}

func (handler *TopologyHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, r, platformgenerated.AppErrorFromConfigInvalid("config snapshot topology routes are read-only"))
		return
	}
	switch r.URL.Path {
	case "/control-plane/platform/catalog/services":
		items, err := handler.facade.ListServiceCatalogEntries(r.Context())
		writeTopologyResult(w, r, map[string]any{"items": items}, err)
	case "/control-plane/platform/topology/planes":
		items, err := handler.facade.ListPlaneBindings(r.Context())
		writeTopologyResult(w, r, map[string]any{"items": items}, err)
	case "/control-plane/platform/topology/prod-plane-access-isolation":
		result, err := handler.facade.GetProdPlaneAccessIsolation(r.Context())
		writeTopologyResult(w, r, result, err)
	case "/control-plane/platform/rollout/routing-policy":
		result, err := handler.facade.GetGrayRoutingPolicy(r.Context())
		writeTopologyResult(w, r, result, err)
	case "/control-plane/platform/topology/environments":
		items, err := handler.facade.ListEnvironmentTopologies(r.Context())
		writeTopologyResult(w, r, map[string]any{"items": items}, err)
	case "/control-plane/platform/topology/clusters":
		items, err := handler.facade.ListRuntimeClusters(r.Context())
		writeTopologyResult(w, r, map[string]any{"items": items}, err)
	default:
		writeError(w, r, platformgenerated.AppErrorFromConfigInvalid("config snapshot topology route is not registered"))
	}
}

func writeTopologyResult(w http.ResponseWriter, r *http.Request, payload any, err error) {
	if err != nil {
		writeError(w, r, platformgenerated.AppErrorFromConfigStorageReadFailed(err.Error()))
		return
	}
	writeJSON(w, http.StatusOK, payload)
}
