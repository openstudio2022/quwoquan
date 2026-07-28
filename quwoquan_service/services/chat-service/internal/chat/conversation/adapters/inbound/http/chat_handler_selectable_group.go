package http

import (
	"net/http"
	"strings"
)

// handleListSelectableGroupConversations 处理 GET /chat/selectable-group-conversations。
// 「从群聊/圈子中选择联系人」来源列表（图四），返回含互关联系人的群 +
// friendMemberCount，并由 source 在服务端区分私建群与圈子绑定群。
func (h *ChatHandler) handleListSelectableGroupConversations(w http.ResponseWriter, r *http.Request) {
	limit := queryInt(r, "limit", 50)
	query := strings.TrimSpace(r.URL.Query().Get("query"))
	source := strings.TrimSpace(r.URL.Query().Get("source"))
	cursor := strings.TrimSpace(r.URL.Query().Get("cursor"))
	page, err := h.memberService.ListSelectableGroupConversations(
		r.Context(),
		resolvePersonaID(r),
		query,
		source,
		limit,
		cursor,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, page)
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
	cursor := strings.TrimSpace(r.URL.Query().Get("cursor"))
	page, err := h.memberService.ListSelectableGroupContactMembers(
		r.Context(),
		resolvePersonaID(r),
		conversationID,
		query,
		limit,
		cursor,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, page)
}
