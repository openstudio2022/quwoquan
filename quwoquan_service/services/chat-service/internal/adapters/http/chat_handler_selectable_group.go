package http

import (
	"net/http"
	"strings"
)

// handleListSelectableGroupConversations 处理 GET /chat/selectable-group-conversations。
// 「从群聊中选择联系人」群列表（图四），返回含互关联系人的群 + friendMemberCount。
func (h *ChatHandler) handleListSelectableGroupConversations(w http.ResponseWriter, r *http.Request) {
	limit := queryInt(r, "limit", 50)
	query := strings.TrimSpace(r.URL.Query().Get("query"))
	rows, err := h.memberService.ListSelectableGroupConversations(
		r.Context(),
		resolveUserID(r),
		query,
		limit,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": rows, "cursor": ""})
}

// handleListSelectableGroupContactMembers 处理
// GET /chat/selectable-group-conversations/{conversationId}/contact-members。
// 「从群聊中选择联系人」群成员列表（图五），返回该群中与当前用户互关的联系人。
func (h *ChatHandler) handleListSelectableGroupContactMembers(w http.ResponseWriter, r *http.Request) {
	conversationID := extractPathParam(
		r.URL.Path,
		"/chat/selectable-group-conversations/{conversationId}/contact-members",
		"conversationId",
	)
	limit := queryInt(r, "limit", 100)
	query := strings.TrimSpace(r.URL.Query().Get("query"))
	items, err := h.memberService.ListSelectableGroupContactMembers(
		r.Context(),
		resolveUserID(r),
		conversationID,
		query,
		limit,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "cursor": ""})
}
