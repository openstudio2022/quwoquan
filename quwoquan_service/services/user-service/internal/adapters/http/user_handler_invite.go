package http

import "net/http"

// 邀请相关 HTTP handler，自 user_handler.go 拆出
// （同 http 包，R03 行数预算，行为不变）。

func (h *UserHandler) handleGenerateInvite(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id required")
		return
	}
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	subAccountID, _ := body["subAccountId"].(string)
	channel, _ := body["channel"].(string)
	inviteePhone, _ := body["inviteePhone"].(string)
	if subAccountID == "" || channel == "" {
		writeInvalidArg(w, r, "subAccountId and channel required")
		return
	}
	record, err := h.invite.Generate(r.Context(), subAccountID, userID, channel, inviteePhone)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, record)
}

func (h *UserHandler) handleListInvites(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id required")
		return
	}
	subAccountID := r.URL.Query().Get("subAccountId")
	statusFilter := r.URL.Query().Get("status")
	records, err := h.invite.ListByInviter(r.Context(), subAccountID, statusFilter, 20, 0)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"invites": records})
}

func (h *UserHandler) handleGetInviteByCode(w http.ResponseWriter, r *http.Request) {
	code := r.PathValue("code")
	record, err := h.invite.GetByCode(r.Context(), code)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	if record == nil {
		writeNotFound(w, r, "resource not found")
		return
	}
	writeJSON(w, http.StatusOK, record)
}

func (h *UserHandler) handleAcceptInvite(w http.ResponseWriter, r *http.Request) {
	code := r.PathValue("code")
	record, err := h.invite.Accept(r.Context(), code)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, record)
}
