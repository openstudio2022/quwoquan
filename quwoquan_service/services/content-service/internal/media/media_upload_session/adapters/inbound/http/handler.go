package http

import (
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	sessionapp "quwoquan_service/services/content-service/internal/media/media_upload_session/application"
)

// Handler owns MediaUploadSession wire parsing and response projection. Route
// discovery remains generated, while the service composition root dispatches
// each generated operation to this object-owned adapter.
type Handler struct {
	useCases *sessionapp.UseCases
}

func NewHandler(useCases *sessionapp.UseCases) *Handler {
	if useCases == nil {
		panic("media upload session HTTP handler requires use cases")
	}
	return &Handler{useCases: useCases}
}

func (h *Handler) Init(w http.ResponseWriter, r *http.Request) {
	var body struct {
		MediaType      string `json:"mediaType"`
		MimeType       string `json:"mimeType"`
		FileSize       int64  `json:"fileSize"`
		ExpectedSHA256 string `json:"expectedSha256"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	result, err := h.useCases.Init(r.Context(), sessionapp.InitCommand{
		OwnerID: actorID(r), MediaType: body.MediaType, MimeType: body.MimeType,
		FileSize: body.FileSize, ExpectedSHA256: body.ExpectedSHA256,
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, responseFromResult(result))
}

func (h *Handler) Complete(w http.ResponseWriter, r *http.Request) {
	var body struct {
		AccessPolicy string `json:"accessPolicy"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil && err != io.EOF {
		writeError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	if strings.TrimSpace(body.AccessPolicy) == "" {
		body.AccessPolicy = "owner_only"
	}
	result, err := h.useCases.Complete(r.Context(), sessionapp.CompleteCommand{
		SessionID: pathValue(r, "sessionId"), OwnerID: actorID(r), AccessPolicy: body.AccessPolicy,
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, responseFromResult(result))
}

func (h *Handler) Abort(w http.ResponseWriter, r *http.Request) {
	result, err := h.useCases.Abort(r.Context(), sessionapp.AbortCommand{
		SessionID: pathValue(r, "sessionId"), OwnerID: actorID(r),
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, responseFromResult(result))
}

func (h *Handler) Get(w http.ResponseWriter, r *http.Request) {
	session, err := h.useCases.Get(r.Context(), sessionapp.GetQuery{
		SessionID: pathValue(r, "sessionId"), OwnerID: actorID(r),
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

type response struct {
	SessionID             string    `json:"sessionId"`
	AssetID               string    `json:"assetId,omitempty"`
	AssetProcessingStatus string    `json:"assetProcessingStatus,omitempty"`
	Status                string    `json:"status"`
	UploadURL             string    `json:"uploadUrl,omitempty"`
	ExpiresAt             time.Time `json:"expiresAt"`
	Replayed              bool      `json:"replayed"`
}

func responseFromResult(result sessionapp.CommandResult) response {
	return response{
		SessionID: result.SessionID, AssetID: result.AssetID, Status: string(result.Status),
		AssetProcessingStatus: result.AssetProcessingStatus,
		UploadURL:             result.UploadURL, ExpiresAt: result.ExpiresAt, Replayed: result.Replayed,
	}
}

func actorID(r *http.Request) string {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		return ""
	}
	actorID, _ := principal.Actor.BusinessActorID()
	return actorID
}

func pathValue(r *http.Request, name string) string {
	if value := strings.TrimSpace(r.PathValue(name)); value != "" {
		return value
	}
	path := strings.TrimPrefix(r.URL.Path, "/content/media/uploads/")
	for _, suffix := range []string{":complete", ":abort"} {
		path = strings.TrimSuffix(path, suffix)
	}
	return strings.TrimSpace(path)
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
