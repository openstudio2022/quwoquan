package config_layer

import (
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"strings"

	configapp "quwoquan_service/control-plane/platform-ops/internal/ops/platform_ops/config_snapshot/application/platform_ops/config_layer"
	platformgenerated "quwoquan_service/control-plane/platform-ops/generated/platform_ops/config_snapshot"
	"quwoquan_service/runtime/controlplane"
	rterr "quwoquan_service/runtime/errors"
)

// Handler 暴露 IaC 配置只读快照查询；不存在任何写路径。
type Handler struct {
	configs *configapp.Facade
}

type ConfigKeyCatalogSlice struct {
	Items []configapp.ConfigKeyDescriptor `json:"items"`
}

func NewHandler(configs *configapp.Facade) (*Handler, error) {
	if configs == nil {
		return nil, errors.New("config snapshot HTTP adapter requires facade")
	}
	return &Handler{configs: configs}, nil
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, r, platformgenerated.AppErrorFromConfigInvalid("config snapshot routes are read-only"))
		return
	}
	switch r.URL.Path {
	case "/control-plane/platform/configs":
		h.listConfigKeys(w, r)
	case "/control-plane/platform/configs/resolve":
		h.resolve(w, r)
	case "/control-plane/platform/configs/snapshot":
		h.snapshot(w, r)
	case "/control-plane/platform/configs/domains":
		h.listDomains(w, r)
	default:
		writeError(w, r, platformgenerated.AppErrorFromConfigInvalid("config route or method is not registered"))
	}
}

func (h *Handler) listConfigKeys(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, ConfigKeyCatalogSlice{Items: h.configs.ListConfigKeys(r.Context())})
}

func (h *Handler) resolve(w http.ResponseWriter, r *http.Request) {
	result, err := h.configs.Resolve(r.Context(), controlplane.ConfigResolutionScope{
		Environment: strings.TrimSpace(r.URL.Query().Get("env")),
		Service:     strings.TrimSpace(r.URL.Query().Get("service")),
	})
	if err != nil {
		writeConfigError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) snapshot(w http.ResponseWriter, r *http.Request) {
	view, err := h.configs.GetSnapshot(
		r.Context(),
		strings.TrimSpace(r.URL.Query().Get("env")),
		strings.TrimSpace(r.URL.Query().Get("service")),
	)
	if err != nil {
		writeConfigError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *Handler) listDomains(w http.ResponseWriter, r *http.Request) {
	domains, err := h.configs.ListDomains(r.Context())
	if err != nil {
		writeConfigError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, domains)
}

func writeConfigError(w http.ResponseWriter, r *http.Request, err error) {
	switch {
	case errors.Is(err, configapp.ErrScopeInvalid):
		writeError(w, r, platformgenerated.AppErrorFromConfigInvalid(err.Error()))
	case errors.Is(err, configapp.ErrSnapshotNotFound), os.IsNotExist(err):
		writeError(w, r, platformgenerated.AppErrorFromConfigSnapshotNotFound("config snapshot not found"))
	default:
		writeError(w, r, platformgenerated.AppErrorFromConfigStorageReadFailed(err.Error()))
	}
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}
