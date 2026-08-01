package http

import (
	"encoding/json"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
	"quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
)

func (h *ChatHandler) registerInternalRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /internal/chat/conversations/direct", h.handleInternalCreateDirect)
	mux.HandleFunc("GET /internal/chat/conversations/direct", h.handleInternalLookupDirect)
}

func (h *ChatHandler) handleInternalCreateDirect(w http.ResponseWriter, r *http.Request) {
	var body struct {
		CreatorID string `json:"creatorId"`
		PeerID    string `json:"peerId"`
		// greetingRequestId 非空表示这条会话是打招呼被回复后升级出来的；
		// openingMessage 是发起者当时写下的那句话，由 peer（发起者）署名落成首条消息。
		GreetingRequestID string                              `json:"greetingRequestId"`
		OpeningMessage    string                              `json:"openingMessage"`
		Intersection      *model.GreetingIntersectionSnapshot `json:"intersectionSnapshot"`
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
	if !isAuthorizedUserServiceRequest(r, creatorID) {
		writeInternalRouteForbidden(w, r)
		return
	}
	greetingID := strings.TrimSpace(body.GreetingRequestID)
	if strings.TrimSpace(body.OpeningMessage) != "" && greetingID == "" {
		// 首条消息只允许作为打招呼升级的一部分写入：没有 greetingRequestId 就没有
		// 「对方已同意」的证据，服务端不得代人向陌生人发话。
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleChat,
			"首条消息必须绑定打招呼请求",
			"openingMessage requires greetingRequestId",
		))
		return
	}
	conv, err := h.conversationService.CreateOrReuseDirect(
		r.Context(),
		creatorID,
		peerID,
		application.DirectConversationPromotion{
			GreetingRequestID: greetingID,
			Intersection:      body.Intersection,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	if greetingID != "" {
		// 发起者是 peer：回复方（creatorID）是被打招呼的人，那句话是 peer 写的。
		// clientMsgId 由 greetingId 派生，回复重放不会写出第二条。
		if err := h.messageService.SendGreetingOpeningMessage(
			r.Context(),
			conv.ID,
			peerID,
			body.OpeningMessage,
			"greeting:"+greetingID,
		); err != nil {
			writeHTTPError(w, r, err)
			return
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"conversationId": conv.ID})
}

func (h *ChatHandler) handleInternalLookupDirect(w http.ResponseWriter, r *http.Request) {
	memberA := strings.TrimSpace(r.URL.Query().Get("memberA"))
	memberB := strings.TrimSpace(r.URL.Query().Get("memberB"))
	if memberA == "" || memberB == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "memberA 与 memberB 必填", "memberA and memberB required"))
		return
	}
	if !isAuthorizedUserServiceRequest(r, memberA) {
		writeInternalRouteForbidden(w, r)
		return
	}
	exists, err := h.conversationService.HasDirectBetween(r.Context(), memberA, memberB)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"exists": exists})
}

func writeInternalRouteForbidden(w http.ResponseWriter, r *http.Request) {
	writeHTTPError(w, r, rterr.NewAppError(
		rterr.NewCode(rterr.ModuleChat, rterr.KindUser, "forbidden"),
		"无权访问内部接口",
		"internal chat route requires delegated user-service persona authorization",
	))
}

func isAuthorizedUserServiceRequest(r *http.Request, personaID string) bool {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok ||
		principal.Subject != "service:user-service" ||
		principal.Actor.PersonaID != strings.TrimSpace(personaID) ||
		!containsGrant(strings.Fields(principal.Scope), "chat.conversation.internal_direct") {
		return false
	}
	return containsGrant(principal.Roles, "service")
}

func containsGrant(grants []string, wanted string) bool {
	for _, grant := range grants {
		if strings.TrimSpace(grant) == wanted {
			return true
		}
	}
	return false
}
