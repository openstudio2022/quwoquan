package http

import (
	"encoding/json"
	"net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
)

func (h *ChatHandler) registerInternalRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /internal/chat/conversations/direct", h.handleInternalCreateDirect)
	mux.HandleFunc("GET /internal/chat/conversations/direct", h.handleInternalLookupDirect)
}

func (h *ChatHandler) handleInternalCreateDirect(w http.ResponseWriter, r *http.Request) {
	if !isInternalServiceRequest(r) {
		writeHTTPError(w, r, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleChat, rterr.KindUser, "forbidden"),
			"无权访问内部接口",
			"internal chat route requires trusted service header",
		))
		return
	}
	var body struct {
		CreatorID string `json:"creatorId"`
		PeerID    string `json:"peerId"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "请求格式错误", err.Error()))
		return
	}
	creatorID := strings.TrimSpace(body.CreatorID)
	peerID := strings.TrimSpace(body.PeerID)
	if creatorID == "" || peerID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "creatorId 与 peerId 必填", "creatorId and peerId required"))
		return
	}
	conv, err := h.conversationService.CreateOrReuseDirect(r.Context(), creatorID, peerID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"conversationId": conv.ID})
}

func (h *ChatHandler) handleInternalLookupDirect(w http.ResponseWriter, r *http.Request) {
	if !isInternalServiceRequest(r) {
		writeHTTPError(w, r, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleChat, rterr.KindUser, "forbidden"),
			"无权访问内部接口",
			"internal chat route requires trusted service header",
		))
		return
	}
	memberA := strings.TrimSpace(r.URL.Query().Get("memberA"))
	memberB := strings.TrimSpace(r.URL.Query().Get("memberB"))
	if memberA == "" || memberB == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "memberA 与 memberB 必填", "memberA and memberB required"))
		return
	}
	exists, err := h.conversationService.HasDirectBetween(r.Context(), memberA, memberB)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"exists": exists})
}

func isInternalServiceRequest(r *http.Request) bool {
	return strings.EqualFold(strings.TrimSpace(r.Header.Get("X-Internal-Service")), "user-service")
}
