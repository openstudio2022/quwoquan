package http

import (
	"net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
)

func (h *ChatHandler) registerMediaUploadRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /v1/chat/media/uploads:init", h.handleInitChatMediaUpload)
	mux.HandleFunc("POST /v1/chat/media/uploads:complete", h.handleCompleteChatMediaUpload)
	mux.HandleFunc("POST /v1/chat/media/uploads:abort", h.handleAbortChatMediaUpload)
}

func (h *ChatHandler) handleInitChatMediaUpload(w http.ResponseWriter, r *http.Request) {
	if h.mediaUploadService == nil {
		writeHTTPError(w, r, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleChat, rterr.KindSystem, "media_upload_not_configured"),
			"聊天媒体上传暂不可用",
			"chat media upload service is not configured",
		))
		return
	}
	var body struct {
		MediaType   string `json:"mediaType"`
		Category    string `json:"category"`
		AssetScope  string `json:"assetScope"`
		SourceKind  string `json:"sourceKind"`
		FileName    string `json:"fileName"`
		ContentType string `json:"contentType"`
		FileSize    int64  `json:"fileSize"`
		OwnerID     string `json:"ownerId"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "请求格式错误", err.Error()))
		return
	}
	mediaType := strings.TrimSpace(body.MediaType)
	if mediaType == "" {
		mediaType = strings.TrimSpace(body.Category)
	}
	resp, err := h.mediaUploadService.InitUpload(
		r.Context(),
		firstNonEmpty(strings.TrimSpace(body.OwnerID), resolveUserID(r)),
		mediaType,
		body.AssetScope,
		body.SourceKind,
		body.FileName,
		body.ContentType,
		body.FileSize,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *ChatHandler) handleCompleteChatMediaUpload(w http.ResponseWriter, r *http.Request) {
	if h.mediaUploadService == nil {
		writeHTTPError(w, r, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleChat, rterr.KindSystem, "media_upload_not_configured"),
			"聊天媒体上传暂不可用",
			"chat media upload service is not configured",
		))
		return
	}
	var body struct {
		SessionID string `json:"sessionId"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "请求格式错误", err.Error()))
		return
	}
	resp, err := h.mediaUploadService.CompleteUpload(r.Context(), body.SessionID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *ChatHandler) handleAbortChatMediaUpload(w http.ResponseWriter, r *http.Request) {
	if h.mediaUploadService == nil {
		writeHTTPError(w, r, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleChat, rterr.KindSystem, "media_upload_not_configured"),
			"聊天媒体上传暂不可用",
			"chat media upload service is not configured",
		))
		return
	}
	var body struct {
		SessionID string `json:"sessionId"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "请求格式错误", err.Error()))
		return
	}
	if err := h.mediaUploadService.AbortUpload(r.Context(), body.SessionID); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"sessionId": strings.TrimSpace(body.SessionID), "status": "aborted"})
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}
