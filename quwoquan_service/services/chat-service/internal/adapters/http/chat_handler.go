package http

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/chat-service/internal/application"
)

type ChatHandler struct {
	conversationService *application.ConversationService
	messageService      *application.MessageService
	memberService       *application.MemberService
	inboxService        *application.InboxService
}

func NewChatHandler(
	conversationService *application.ConversationService,
	messageService *application.MessageService,
	memberService *application.MemberService,
	inboxService *application.InboxService,
) *ChatHandler {
	return &ChatHandler{
		conversationService: conversationService,
		messageService:      messageService,
		memberService:       memberService,
		inboxService:        inboxService,
	}
}

func (h *ChatHandler) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", h.handleHealthz)
	mux.HandleFunc("GET /v1/chat/conversations/search", h.handleSearchConversations)
	mux.HandleFunc("GET /v1/chat/messages/search", h.handleSearchMessages)
	mux.HandleFunc("PATCH /v1/chat/conversations/{conversationId}/owner", h.handleTransferOwnership)
	mux.HandleFunc("PUT /v1/chat/conversations/{conversationId}/admins", h.handleUpdateGroupAdmins)
	mux.HandleFunc("DELETE /v1/chat/conversations/{conversationId}", h.handleDissolveConversation)
	RegisterGeneratedRoutes(mux, h)
	return mux
}

func (h *ChatHandler) handleHealthz(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

// ── Conversation ─────────────────────────────────────────────────────────────

func (h *ChatHandler) handleListConversations(w http.ResponseWriter, r *http.Request) {
	userId := resolveUserID(r)
	cursor := r.URL.Query().Get("cursor")
	limit := queryInt(r, "limit", 20)

	convs, err := h.conversationService.ListConversations(r.Context(), application.ListConversationsRequest{
		UserId: userId, Cursor: cursor, Limit: limit,
	})
	if err != nil {
		writeHTTPError(w, err)
		return
	}

	nextCursor := ""
	if len(convs) > 0 {
		nextCursor = convs[len(convs)-1].ID
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items": convs, "cursor": nextCursor,
	})
}

func (h *ChatHandler) handleCreateConversation(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Type             string   `json:"type"`
		Title            string   `json:"title"`
		CircleId         string   `json:"circleId"`
		MaxGroupSize     int      `json:"maxGroupSize"`
		InitialMemberIds []string `json:"initialMemberIds"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}

	conv, err := h.conversationService.CreateConversation(r.Context(), application.CreateConversationRequest{
		Type: body.Type, Title: body.Title, CircleId: body.CircleId,
		MaxGroupSize: body.MaxGroupSize, CreatorId: resolveUserID(r), InitialMemberIds: body.InitialMemberIds,
	})
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, conv)
}

func (h *ChatHandler) handleGetConversation(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}", "conversationId")
	conv, err := h.conversationService.GetConversation(r.Context(), convId)
	if err != nil {
		writeHTTPError(w, newNotFound("会话", convId))
		return
	}
	writeJSON(w, http.StatusOK, conv)
}

// ── Messages ─────────────────────────────────────────────────────────────────

func (h *ChatHandler) handleListMessages(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/messages", "conversationId")
	limit := queryInt(r, "limit", 20)
	afterSeq := queryInt64(r, "afterSeq", 0)
	beforeSeq := queryInt64(r, "beforeSeq", 0)

	msgs, err := h.messageService.ListMessages(r.Context(), application.ListMessagesRequest{
		ConversationId: convId, Limit: limit, AfterSeq: afterSeq, BeforeSeq: beforeSeq,
	})
	if err != nil {
		writeHTTPError(w, err)
		return
	}

	cursor := ""
	if len(msgs) > 0 {
		cursor = msgs[len(msgs)-1].ID
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items": msgs, "cursor": cursor,
	})
}

func (h *ChatHandler) handleSendMessage(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/messages", "conversationId")
	var body struct {
		Type             string         `json:"type"`
		Content          string         `json:"content"`
		MediaUrl         string         `json:"mediaUrl"`
		Media            map[string]any `json:"media"`
		CardPayload      map[string]any `json:"cardPayload"`
		ReplyToMessageId string         `json:"replyToMessageId"`
		Mentions         []string       `json:"mentions"`
		ClientMsgId      string         `json:"clientMsgId"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}

	resp, err := h.messageService.SendMessage(r.Context(), application.SendMessageRequest{
		ConversationId: convId, SenderId: resolveUserID(r), Type: body.Type,
		Content: body.Content, MediaUrl: body.MediaUrl, Media: body.Media, CardPayload: body.CardPayload,
		ReplyToMessageId: body.ReplyToMessageId, Mentions: body.Mentions, ClientMsgId: body.ClientMsgId,
	})
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, resp)
}

func (h *ChatHandler) handleRecallMessage(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/messages/{messageId}/recall", "conversationId")
	msgId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/messages/{messageId}/recall", "messageId")

	err := h.messageService.RecallMessage(r.Context(), convId, msgId, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "recalled"})
}

func (h *ChatHandler) handleSyncMessages(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/sync", "conversationId")
	var body struct {
		LastSeq int64 `json:"lastSeq"`
		Limit   int   `json:"limit"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}

	resp, err := h.messageService.SyncMessages(r.Context(), application.SyncMessagesRequest{
		ConversationId: convId, LastSeq: body.LastSeq, Limit: body.Limit,
	})
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *ChatHandler) handleMarkAsRead(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/messages/{messageId}/read", "conversationId")
	msgId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/messages/{messageId}/read", "messageId")

	err := h.messageService.MarkAsRead(r.Context(), application.MarkAsReadRequest{
		ConversationId: convId, MessageId: msgId, UserId: resolveUserID(r),
	})
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *ChatHandler) handleGetReceipts(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/messages/{messageId}/receipts", "conversationId")
	msgId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/messages/{messageId}/receipts", "messageId")
	_ = convId

	receipts, err := h.messageService.GetReceipts(r.Context(), convId, msgId)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": receipts})
}

// ── Members ──────────────────────────────────────────────────────────────────

func (h *ChatHandler) handleListMembers(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/members", "conversationId")
	cursor := r.URL.Query().Get("cursor")
	limit := queryInt(r, "limit", 20)
	role := r.URL.Query().Get("role")

	members, err := h.memberService.ListMembers(r.Context(), application.ListMembersRequest{
		ConversationId: convId, Cursor: cursor, Limit: limit, Role: role,
	})
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": members})
}

func (h *ChatHandler) handleAddMembers(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/members", "conversationId")
	var body struct {
		UserIds []string `json:"userIds"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}

	err := h.memberService.AddMembers(r.Context(), application.AddMembersRequest{
		ConversationId: convId, UserIds: body.UserIds, InvitedBy: resolveUserID(r),
	})
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *ChatHandler) handleRemoveMember(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/members/{userId}", "conversationId")
	userId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/members/{userId}", "userId")

	err := h.memberService.RemoveMember(r.Context(), convId, userId)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *ChatHandler) handleInviteAssistant(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/assistant", "conversationId")
	var body struct {
		SkillId string `json:"skillId"`
	}
	_ = readJSON(r, &body)

	err := h.memberService.InviteAssistant(r.Context(), application.InviteAssistantRequest{
		ConversationId: convId, SkillId: body.SkillId, InvitedBy: resolveUserID(r),
	})
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *ChatHandler) handleRemoveAssistant(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/assistant", "conversationId")

	err := h.memberService.RemoveAssistant(r.Context(), convId)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *ChatHandler) handleUpdateConversationSettings(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/settings", "conversationId")
	var body struct {
		Muted  *bool `json:"muted"`
		Pinned *bool `json:"pinned"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}

	err := h.conversationService.UpdateSettings(r.Context(), application.UpdateSettingsRequest{
		UserId: resolveUserID(r), ConversationId: convId, Muted: body.Muted, Pinned: body.Pinned,
	})
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *ChatHandler) handleTransferOwnership(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/owner", "conversationId")
	var body struct {
		NewOwnerId string `json:"newOwnerId"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}
	err := h.memberService.TransferOwnership(r.Context(), application.TransferOwnershipRequest{
		ConversationId: convId,
		OperatorId:     resolveUserID(r),
		NewOwnerId:     body.NewOwnerId,
	})
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *ChatHandler) handleUpdateGroupAdmins(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/admins", "conversationId")
	var body struct {
		AdminIds []string `json:"adminIds"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}
	err := h.memberService.UpdateGroupAdmins(r.Context(), application.UpdateGroupAdminsRequest{
		ConversationId: convId,
		OperatorId:     resolveUserID(r),
		AdminIds:       body.AdminIds,
	})
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *ChatHandler) handleDissolveConversation(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}", "conversationId")
	err := h.conversationService.DissolveConversation(r.Context(), application.DissolveConversationRequest{
		ConversationId: convId,
		OperatorId:     resolveUserID(r),
	})
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

// ── Inbox ────────────────────────────────────────────────────────────────────

func (h *ChatHandler) handleListInbox(w http.ResponseWriter, r *http.Request) {
	userId := resolveUserID(r)
	cursor := r.URL.Query().Get("cursor")
	limit := queryInt(r, "limit", 50)

	items, err := h.inboxService.ListInbox(r.Context(), application.ListInboxRequest{
		UserId: userId, Cursor: cursor, Limit: limit,
	})
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

// ── Contacts ─────────────────────────────────────────────────────────────────

func (h *ChatHandler) handleListContacts(w http.ResponseWriter, r *http.Request) {
	cursor := r.URL.Query().Get("cursor")
	limit := queryInt(r, "limit", 20)

	contacts, err := h.memberService.ListContacts(r.Context(), resolveUserID(r), limit, cursor)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": contacts})
}

func (h *ChatHandler) handleSearchContacts(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query().Get("query")
	if query == "" {
		query = r.URL.Query().Get("q")
	}
	limit := queryInt(r, "limit", 20)
	contacts, err := h.memberService.SearchContacts(
		r.Context(),
		resolveUserID(r),
		query,
		limit,
	)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	items := make([]map[string]any, 0, len(contacts))
	cursor := ""
	for _, contact := range contacts {
		cursor = contact.ContactID
		items = append(items, map[string]any{
			"contactId":        contact.ContactID,
			"displayName":      contact.DisplayName,
			"avatarUrl":        contact.AvatarURL,
			"conversationId":   contact.ConversationID,
			"conversationType": contact.ConversationType,
			"subtitle":         contact.Subtitle,
			"highlightText":    contact.HighlightText,
			"matchedField":     contact.MatchedField,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "cursor": cursor})
}

func (h *ChatHandler) handleSearchConversations(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query().Get("query")
	limit := queryInt(r, "limit", 20)
	conversations, err := h.conversationService.SearchConversations(
		r.Context(),
		application.SearchConversationsRequest{
			UserId: resolveUserID(r),
			Query:  query,
			Cursor: r.URL.Query().Get("cursor"),
			Limit:  limit,
		},
	)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	items := make([]map[string]any, 0, len(conversations))
	cursor := ""
	for _, conversation := range conversations {
		cursor = conversation.ID
		highlight := strings.TrimSpace(conversation.LastMessagePreview)
		if highlight == "" {
			highlight = conversation.Title
		}
		items = append(items, map[string]any{
			"conversationId":     conversation.ID,
			"type":               conversation.Type,
			"title":              conversation.Title,
			"avatarUrl":          conversation.AvatarUrl,
			"lastMessagePreview": conversation.LastMessagePreview,
			"lastMessageTime":    conversation.LastMessageTime,
			"memberCount":        conversation.MemberCount,
			"circleId":           conversation.CircleId,
			"highlightText":      highlight,
			"matchedField":       "title",
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "cursor": cursor})
}

func (h *ChatHandler) handleSearchMessages(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query().Get("query")
	limit := queryInt(r, "limit", 20)
	hits, err := h.messageService.SearchMessages(
		r.Context(),
		application.SearchMessagesRequest{
			UserId: resolveUserID(r),
			Query:  query,
			Cursor: r.URL.Query().Get("cursor"),
			Limit:  limit,
		},
	)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	items := make([]map[string]any, 0, len(hits))
	cursor := ""
	for _, hit := range hits {
		cursor = hit.Message.ID
		items = append(items, map[string]any{
			"messageId":              hit.Message.ID,
			"conversationId":         hit.Conversation.ID,
			"conversationTitle":      hit.Conversation.Title,
			"conversationAvatarUrl":  hit.Conversation.AvatarUrl,
			"senderProfileSubjectId": "",
			"senderDisplayName":      hit.Message.SenderId,
			"senderAvatarUrl":        "",
			"messageType":            hit.Message.Type,
			"contentSnippet":         hit.Message.Content,
			"highlightText":          hit.Message.Content,
			"matchedField":           "content",
			"timestamp":              hit.Message.Timestamp,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "cursor": cursor})
}

// ── Helpers ──────────────────────────────────────────────────────────────────

func resolveUserID(r *http.Request) string {
	return r.Header.Get("X-Client-User-Id")
}

func writeJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(data)
}

func writeHTTPError(w http.ResponseWriter, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptions{})
}

func newNotFound(entity, id string) *rterr.AppError {
	return rterr.NewAppError(
		rterr.NewCode(rterr.ModuleChat, rterr.KindUser, "not_found"),
		entity+"不存在",
		entity+" not found: "+id,
		false,
	)
}

func readJSON(r *http.Request, v any) error {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		return err
	}
	return json.Unmarshal(body, v)
}

func queryInt(r *http.Request, key string, defaultVal int) int {
	s := r.URL.Query().Get(key)
	if s == "" {
		return defaultVal
	}
	v, err := strconv.Atoi(s)
	if err != nil {
		return defaultVal
	}
	return v
}

func queryInt64(r *http.Request, key string, defaultVal int64) int64 {
	s := r.URL.Query().Get(key)
	if s == "" {
		return defaultVal
	}
	v, err := strconv.ParseInt(s, 10, 64)
	if err != nil {
		return defaultVal
	}
	return v
}
