package http

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/content-service/generated/content/post"
	contentpublic "quwoquan_service/services/content-service/internal/content/post/application/public"
)

// ActiveReleaseFenceHandler 只投影已有 public port，不持有 activation 或存储写能力。
type ActiveReleaseFenceHandler struct {
	reader      contentpublic.ActiveReleaseFenceQueryPort
	environment string
}

func NewActiveReleaseFenceHandler(reader contentpublic.ActiveReleaseFenceQueryPort, environment string) *ActiveReleaseFenceHandler {
	return &ActiveReleaseFenceHandler{reader: contentpublic.NewActiveReleaseFenceQueryFacade(reader), environment: environment}
}

func (h *ActiveReleaseFenceHandler) Register(mux *http.ServeMux) {
	mux.HandleFunc(generated.RouteReadActiveReleaseFenceMethod+" "+generated.RouteReadActiveReleaseFencePath, h.read)
}

// activeReleaseFenceResponse 严格对应 Post fields.yaml ContentActiveReleaseFence。
type activeReleaseFenceResponse struct {
	Found             bool       `json:"found"`
	Environment       string     `json:"environment"`
	SourceOwner       string     `json:"sourceOwner"`
	ReleaseID         string     `json:"releaseId"`
	ManifestDigest    string     `json:"manifestDigest"`
	Revision          int64      `json:"revision"`
	ProjectionVersion int64      `json:"projectionVersion"`
	ActivatedAt       *time.Time `json:"activatedAt"`
}

func (h *ActiveReleaseFenceHandler) read(w http.ResponseWriter, r *http.Request) {
	query := contentpublic.ActiveReleaseFenceQuery{Environment: r.URL.Query().Get("environment"), SourceOwner: r.URL.Query().Get("sourceOwner")}
	if h.environment == "" || query.Environment != h.environment || query.SourceOwner != "qwq_data" {
		rterr.WriteHTTPError(w, generated.AppErrorFromInvalidArgument("active fence query must match deployment environment and Data owner"), rterr.HTTPWriteOptionsFromRequest(r))
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 500*time.Millisecond)
	defer cancel()
	fence, err := h.reader.ReadActiveReleaseFence(ctx, query)
	if err != nil {
		rterr.WriteHTTPError(w, generated.AppErrorFromStorageReadFailed("Content active release fence read failed"), rterr.HTTPWriteOptionsFromRequest(r))
		return
	}
	response := activeReleaseFenceResponse{Found: fence.Found, Environment: fence.Environment, SourceOwner: fence.SourceOwner, ReleaseID: fence.ReleaseID, ManifestDigest: fence.ManifestDigest, Revision: fence.Revision, ProjectionVersion: fence.ProjectionVersion}
	if fence.Found {
		response.ActivatedAt = &fence.ActivatedAt
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	_ = json.NewEncoder(w).Encode(response)
}
