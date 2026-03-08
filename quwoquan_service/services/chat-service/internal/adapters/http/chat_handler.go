package http

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"

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
		Type         string `json:"type"`
		Title        string `json:"title"`
		CircleId     string `json:"circleId"`
		MaxGroupSize int    `json:"maxGroupSize"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}

	conv, err := h.conversationService.CreateConversation(r.Context(), application.CreateConversationRequest{
		Type: body.Type, Title: body.Title, CircleId: body.CircleId,
		MaxGroupSize: body.MaxGroupSize, CreatorId: resolveUserID(r),
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
	query := r.URL.Query().Get("q")
	contacts, err := h.memberService.SearchContacts(r.Context(), query)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": contacts})
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
