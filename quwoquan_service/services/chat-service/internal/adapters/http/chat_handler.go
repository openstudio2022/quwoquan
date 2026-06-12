package http

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	runtimesync "quwoquan_service/runtime/sync"
	"quwoquan_service/services/chat-service/internal/application"
	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
)

type ChatHandler struct {
	conversationService *application.ConversationService
	messageService      *application.MessageService
	memberService       *application.MemberService
	inboxService        *application.InboxService
	mediaUploadService  *application.ChatMediaUploadService
	userSyncService     *runtimesync.Service
}

func NewChatHandler(
	conversationService *application.ConversationService,
	messageService *application.MessageService,
	memberService *application.MemberService,
	inboxService *application.InboxService,
	userSyncService *runtimesync.Service,
) *ChatHandler {
	return &ChatHandler{
		conversationService: conversationService,
		messageService:      messageService,
		memberService:       memberService,
		inboxService:        inboxService,
		mediaUploadService:  application.NewChatMediaUploadService(),
		userSyncService:     userSyncService,
	}
}

func (h *ChatHandler) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", h.handleHealthz)
	mux.HandleFunc("POST /v1/user/sync", h.handlePullUserSync)
	mux.HandleFunc("GET /v1/chat/conversations/search", h.handleSearchConversations)
	mux.HandleFunc("GET /v1/chat/messages/search", h.handleSearchMessages)
	mux.HandleFunc("PATCH /v1/chat/conversations/{conversationId}", h.handleUpdateConversationTitle)
	mux.HandleFunc("GET /v1/chat/message-home", h.handleListMessageHome)
	mux.HandleFunc("GET /v1/chat/contact-home", h.handleListContactHome)
	mux.HandleFunc("GET /v1/chat/groups/{conversationId}/home", h.handleGetGroupHome)
	mux.HandleFunc("PATCH /v1/chat/conversations/{conversationId}/owner", h.handleTransferOwnership)
	mux.HandleFunc("PUT /v1/chat/conversations/{conversationId}/admins", h.handleUpdateGroupAdmins)
	mux.HandleFunc("DELETE /v1/chat/conversations/{conversationId}", h.handleDissolveConversation)
	h.registerMediaUploadRoutes(mux)
	RegisterGeneratedRoutes(mux, h)
	h.registerInternalRoutes(mux)
	return mux
}

func (h *ChatHandler) handleHealthz(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *ChatHandler) handlePullUserSync(w http.ResponseWriter, r *http.Request) {
	if h.userSyncService == nil {
		writeHTTPError(
			w,
			r,
			rterr.NewAppError(
				rterr.NewCode(rterr.ModuleChat, rterr.KindSystem, "sync_not_configured"),
				"同步暂不可用",
				"chat user sync service is not configured",
			),
		)
		return
	}
	userID := resolveUserID(r)
	if userID == "" {
		writeHTTPError(
			w,
			r,
			rterr.NewInvalidArgument(rterr.ModuleChat, "X-Client-User-Id header required", "missing X-Client-User-Id"),
		)
		return
	}
	var body struct {
		AfterSeq int64 `json:"afterSeq"`
		Limit    int   `json:"limit"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}
	resp, err := h.userSyncService.Pull(r.Context(), userID, body.AfterSeq, body.Limit)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
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
		writeHTTPError(w, r, err)
		return
	}

	nextCursor := ""
	if len(convs) > 0 {
		nextCursor = convs[len(convs)-1].ID
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items": h.flattenConversations(r.Context(), convs), "cursor": nextCursor,
	})
}

func (h *ChatHandler) handleCreateConversation(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Type             string   `json:"type"`
		Title            string   `json:"title"`
		CircleId         string   `json:"circleId"`
		CircleGroupId    string   `json:"circleGroupId"`
		EntityId         string   `json:"entityId"`
		OriginType       string   `json:"originType"`
		BindingType      string   `json:"bindingType"`
		LifecyclePolicy  string   `json:"lifecyclePolicy"`
		MaxGroupSize     int      `json:"maxGroupSize"`
		InitialMemberIds []string `json:"initialMemberIds"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}

	conv, err := h.conversationService.CreateConversation(r.Context(), application.CreateConversationRequest{
		Type: body.Type, Title: body.Title, CircleId: body.CircleId, CircleGroupId: body.CircleGroupId, EntityId: body.EntityId,
		OriginType: body.OriginType, BindingType: body.BindingType, LifecyclePolicy: body.LifecyclePolicy,
		MaxGroupSize: body.MaxGroupSize, CreatorId: resolveUserID(r), InitialMemberIds: body.InitialMemberIds,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, h.conversationToWire(r.Context(), *conv))
}

func (h *ChatHandler) handleGetConversation(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}", "conversationId")
	conv, err := h.conversationService.GetConversation(r.Context(), convId)
	if err != nil {
		writeHTTPError(w, r, newNotFound("会话", convId))
		return
	}
	writeJSON(w, http.StatusOK, h.conversationToWire(r.Context(), *conv))
}

func (h *ChatHandler) handleUpdateConversationTitle(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}", "conversationId")
	var body struct {
		Title string `json:"title"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}
	conv, err := h.conversationService.UpdateConversationTitle(r.Context(), application.UpdateConversationTitleRequest{
		ConversationId: convId,
		OperatorId:     resolveUserID(r),
		Title:          body.Title,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, h.conversationToWire(r.Context(), *conv))
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
		writeHTTPError(w, r, err)
		return
	}

	cursor := ""
	if len(msgs) > 0 {
		cursor = msgs[len(msgs)-1].ID
	}
	items := make([]map[string]any, 0, len(msgs))
	for i := range msgs {
		items = append(items, messageToWire(msgs[i]))
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items": items, "cursor": cursor,
	})
}

func (h *ChatHandler) handleSendMessage(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/messages", "conversationId")
	var body struct {
		Type                      string         `json:"type"`
		Content                   string         `json:"content"`
		MediaUrl                  string         `json:"mediaUrl"`
		Media                     map[string]any `json:"media"`
		CardPayload               map[string]any `json:"cardPayload"`
		ReplyToMessageId          string         `json:"replyToMessageId"`
		Mentions                  []string       `json:"mentions"`
		ClientMsgId               string         `json:"clientMsgId"`
		SenderSubAccountId        string         `json:"senderSubAccountId"`
		PersonaContextVersion     int64          `json:"personaContextVersion"`
		SenderDisplayNameSnapshot string         `json:"senderDisplayNameSnapshot"`
		SenderAvatarUrlSnapshot   string         `json:"senderAvatarUrlSnapshot"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}

	senderID := strings.TrimSpace(r.Header.Get("X-Client-Sub-Account-Id"))
	if senderID == "" {
		senderID = resolveUserID(r)
	}
	if senderID == "" {
		senderID = strings.TrimSpace(body.SenderSubAccountId)
	}
	if senderID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleChat,
			"缺少 X-Client-Sub-Account-Id",
			"missing X-Client-Sub-Account-Id",
		))
		return
	}
	resp, err := h.messageService.SendMessage(r.Context(), application.SendMessageRequest{
		ConversationId: convId, SenderId: senderID,
		PersonaContextVersion:     body.PersonaContextVersion,
		SenderDisplayNameSnapshot: strings.TrimSpace(body.SenderDisplayNameSnapshot),
		SenderAvatarUrlSnapshot:   strings.TrimSpace(body.SenderAvatarUrlSnapshot), Type: body.Type,
		Content: body.Content, MediaUrl: body.MediaUrl, Media: body.Media, CardPayload: body.CardPayload,
		ReplyToMessageId: body.ReplyToMessageId, Mentions: body.Mentions, ClientMsgId: body.ClientMsgId,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, resp)
}

func (h *ChatHandler) handleRecallMessage(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/messages/{messageId}/recall", "conversationId")
	msgId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/messages/{messageId}/recall", "messageId")

	err := h.messageService.RecallMessage(r.Context(), convId, msgId, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, r, err)
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
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}

	resp, err := h.messageService.SyncMessages(r.Context(), application.SyncMessagesRequest{
		ConversationId: convId, LastSeq: body.LastSeq, Limit: body.Limit,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	items := make([]map[string]any, 0, len(resp.Messages))
	for i := range resp.Messages {
		items = append(items, messageToWire(resp.Messages[i]))
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"messages": items,
		"hasMore":  resp.HasMore,
	})
}

func (h *ChatHandler) handleMarkAsRead(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/messages/{messageId}/read", "conversationId")
	msgId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/messages/{messageId}/read", "messageId")

	err := h.messageService.MarkAsRead(r.Context(), application.MarkAsReadRequest{
		ConversationId: convId, MessageId: msgId, UserId: resolveUserID(r),
	})
	if err != nil {
		writeHTTPError(w, r, err)
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
		writeHTTPError(w, r, err)
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

	sort := r.URL.Query().Get("sort")
	members, err := h.memberService.ListMembers(r.Context(), application.ListMembersRequest{
		ConversationId: convId, Cursor: cursor, Limit: limit, Role: role, Sort: sort,
	})
	if err != nil {
		writeHTTPError(w, r, err)
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
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}

	err := h.memberService.AddMembers(r.Context(), application.AddMembersRequest{
		ConversationId: convId, UserIds: body.UserIds, InvitedBy: resolveUserID(r),
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *ChatHandler) handleRemoveMember(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/members/{userId}", "conversationId")
	userId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/members/{userId}", "userId")

	err := h.memberService.RemoveMember(r.Context(), convId, userId)
	if err != nil {
		writeHTTPError(w, r, err)
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
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *ChatHandler) handleRemoveAssistant(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/conversations/{conversationId}/assistant", "conversationId")

	err := h.memberService.RemoveAssistant(r.Context(), convId)
	if err != nil {
		writeHTTPError(w, r, err)
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
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}

	err := h.conversationService.UpdateSettings(r.Context(), application.UpdateSettingsRequest{
		UserId: resolveUserID(r), ConversationId: convId, Muted: body.Muted, Pinned: body.Pinned,
	})
	if err != nil {
		writeHTTPError(w, r, err)
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
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}
	err := h.memberService.TransferOwnership(r.Context(), application.TransferOwnershipRequest{
		ConversationId: convId,
		OperatorId:     resolveUserID(r),
		NewOwnerId:     body.NewOwnerId,
	})
	if err != nil {
		writeHTTPError(w, r, err)
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
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}
	err := h.memberService.UpdateGroupAdmins(r.Context(), application.UpdateGroupAdminsRequest{
		ConversationId: convId,
		OperatorId:     resolveUserID(r),
		AdminIds:       body.AdminIds,
	})
	if err != nil {
		writeHTTPError(w, r, err)
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
		writeHTTPError(w, r, err)
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
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": h.flattenInboxItems(r.Context(), items)})
}

func (h *ChatHandler) handleListMessageHome(w http.ResponseWriter, r *http.Request) {
	userId := resolveUserID(r)
	cursor := r.URL.Query().Get("cursor")
	limit := queryInt(r, "limit", 50)
	filter := normalizeMessageHomeFilter(r.URL.Query().Get("filter"))

	items, err := h.inboxService.ListInbox(r.Context(), application.ListInboxRequest{
		UserId: userId, Cursor: cursor, Limit: limit,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	rows := make([]map[string]any, 0, len(items))
	for _, item := range items {
		if !messageHomeMatchesFilter(item, filter) {
			continue
		}
		rows = append(rows, h.messageHomeRowToWire(r.Context(), item))
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": rows})
}

// ── Contacts ─────────────────────────────────────────────────────────────────

func (h *ChatHandler) handleListContacts(w http.ResponseWriter, r *http.Request) {
	cursor := r.URL.Query().Get("cursor")
	limit := queryInt(r, "limit", 20)

	contacts, err := h.memberService.ListContacts(r.Context(), resolveUserID(r), limit, cursor)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": contacts})
}

func (h *ChatHandler) handleListContactHome(w http.ResponseWriter, r *http.Request) {
	cursor := r.URL.Query().Get("cursor")
	limit := queryInt(r, "limit", 50)
	filter := normalizeContactHomeFilter(r.URL.Query().Get("filter"))
	userID := resolveUserID(r)

	rows := make([]map[string]any, 0, limit)
	if filter == "all" || filter == "mutual" {
		contacts, err := h.memberService.ListContacts(r.Context(), userID, limit, cursor)
		if err != nil {
			writeHTTPError(w, r, err)
			return
		}
		for _, contact := range contacts {
			if filter == "mutual" && stringFromMap(contact, "relationState") != "mutual" {
				continue
			}
			rows = append(rows, contactHomeUserRowToWire(contact))
			if len(rows) >= limit {
				writeJSON(w, http.StatusOK, map[string]any{"items": rows})
				return
			}
		}
	}
	if filter == "all" || filter == "group" {
		conversations, err := h.conversationService.ListConversations(r.Context(), application.ListConversationsRequest{
			UserId: userID,
			Limit:  limit,
			Cursor: cursor,
		})
		if err != nil {
			writeHTTPError(w, r, err)
			return
		}
		for _, conversation := range conversations {
			if conversation.Type != "group" {
				continue
			}
			rows = append(rows, h.contactHomeGroupRowToWire(r.Context(), conversation))
			if len(rows) >= limit {
				break
			}
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": rows})
}

func (h *ChatHandler) handleGetGroupHome(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/v1/chat/groups/{conversationId}/home", "conversationId")
	conv, err := h.conversationService.GetConversation(r.Context(), convId)
	if err != nil {
		writeHTTPError(w, r, newNotFound("会话", convId))
		return
	}
	if conv.Type != "group" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "不是群聊会话", "conversation is not a group"))
		return
	}
	writeJSON(w, http.StatusOK, h.groupHomeToWire(r.Context(), *conv, resolveUserID(r)))
}

func (h *ChatHandler) handleListGroupCandidates(w http.ResponseWriter, r *http.Request) {
	limit := queryInt(r, "limit", 100)
	conversationID := strings.TrimSpace(r.URL.Query().Get("conversationId"))
	candidates, err := h.memberService.ListGroupCandidates(
		r.Context(),
		resolveUserID(r),
		conversationID,
		limit,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": candidates, "cursor": ""})
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
		writeHTTPError(w, r, err)
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
			"source":           contact.Source,
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
		writeHTTPError(w, r, err)
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
			"avatarUrl":          h.resolveConversationAvatarURL(r.Context(), conversation),
			"groupAvatarVersion": conversation.GroupAvatarVersion,
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
		writeHTTPError(w, r, err)
		return
	}
	items := make([]map[string]any, 0, len(hits))
	cursor := ""
	for _, hit := range hits {
		cursor = hit.Message.ID
		items = append(items, map[string]any{
			"messageId":             hit.Message.ID,
			"conversationId":        hit.Conversation.ID,
			"conversationTitle":     hit.Conversation.Title,
			"conversationAvatarUrl": h.resolveConversationAvatarURL(r.Context(), hit.Conversation),
			"senderSubAccountId":    hit.Message.SenderId,
			"senderDisplayName":     hit.Message.SenderId,
			"senderAvatarUrl":       "",
			"messageType":           hit.Message.Type,
			"contentSnippet":        hit.Message.Content,
			"highlightText":         hit.Message.Content,
			"matchedField":          "content",
			"timestamp":             hit.Message.Timestamp,
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

func (h *ChatHandler) flattenConversations(ctx context.Context, convs []model.Conversation) []map[string]any {
	items := make([]map[string]any, 0, len(convs))
	for _, conv := range convs {
		items = append(items, h.conversationToWire(ctx, conv))
	}
	return items
}

func (h *ChatHandler) flattenInboxItems(ctx context.Context, items []application.InboxItem) []map[string]any {
	out := make([]map[string]any, 0, len(items))
	for _, item := range items {
		out = append(out, h.inboxItemToWire(ctx, item))
	}
	return out
}

func (h *ChatHandler) inboxItemToWire(ctx context.Context, item application.InboxItem) map[string]any {
	conv := h.conversationToWire(ctx, item.Conversation)
	conv["lastSeq"] = item.Conversation.MaxSeq
	conv["unreadCount"] = item.UserState.UnreadCount
	conv["mentionUnreadCount"] = 0
	conv["muted"] = item.UserState.Muted
	conv["pinned"] = item.UserState.Pinned
	return conv
}

func (h *ChatHandler) messageHomeRowToWire(ctx context.Context, item application.InboxItem) map[string]any {
	conv := h.inboxItemToWire(ctx, item)
	return map[string]any{
		"id":                 item.Conversation.ID,
		"kind":               "conversation",
		"conversationId":     item.Conversation.ID,
		"notificationId":     "",
		"conversationType":   item.Conversation.Type,
		"title":              item.Conversation.Title,
		"summary":            item.Conversation.LastMessagePreview,
		"avatarUrl":          conv["avatarUrl"],
		"groupAvatarVersion": item.Conversation.GroupAvatarVersion,
		"lastActiveAt":       item.Conversation.LastMessageTime,
		"unreadCount":        item.UserState.UnreadCount,
		"mentionUnreadCount": 0,
		"muted":              item.UserState.Muted,
		"pinned":             item.UserState.Pinned,
		"notificationType":   "",
		"read":               item.UserState.UnreadCount == 0,
	}
}

func contactHomeUserRowToWire(contact map[string]any) map[string]any {
	contactID := firstStringFromMap(contact, "contactId", "userId", "id")
	displayName := firstStringFromMap(contact, "displayName", "name")
	metFrom := stringFromMap(contact, "metFrom")
	bio := stringFromMap(contact, "bio")
	lastInteraction := stringFromMap(contact, "lastInteraction")
	return map[string]any{
		"id":                   contactID,
		"kind":                 "user",
		"objectId":             contactID,
		"userId":               contactID,
		"conversationId":       stringFromMap(contact, "conversationId"),
		"title":                displayName,
		"subtitle":             stringFromMap(contact, "subtitle"),
		"avatarUrl":            stringFromMap(contact, "avatarUrl"),
		"relationState":        stringFromMap(contact, "relationState"),
		"summaryIntersections": firstTwoNonEmpty(metFrom, bio),
		"lastActiveAt":         parseOptionalRFC3339(lastInteraction),
		"sortKey":              lastInteraction,
		"isStarred":            boolFromMap(contact, "isStarred"),
	}
}

func (h *ChatHandler) contactHomeGroupRowToWire(ctx context.Context, conv model.Conversation) map[string]any {
	sourceSummary := joinNonEmpty(" · ", conv.CircleId, conv.EntityId)
	return map[string]any{
		"id":                   conv.ID,
		"kind":                 "group",
		"objectId":             conv.ID,
		"conversationId":       conv.ID,
		"circleId":             conv.CircleId,
		"circleGroupId":        conv.CircleGroupId,
		"entityId":             conv.EntityId,
		"title":                conv.Title,
		"subtitle":             sourceSummary,
		"avatarUrl":            h.resolveConversationAvatarURL(ctx, conv),
		"summaryIntersections": firstTwoNonEmpty(conv.CircleId, conv.EntityId),
		"sourceEntityTitle":    conv.EntityId,
		"sourceCircleTitle":    conv.CircleId,
		"memberCount":          conv.MemberCount,
		"lastActiveAt":         conv.LastMessageTime,
		"sortKey":              conv.LastMessageTime.UTC().Format(time.RFC3339),
	}
}

func (h *ChatHandler) groupHomeToWire(ctx context.Context, conv model.Conversation, userID string) map[string]any {
	role := ""
	if userID != "" && h.memberService != nil {
		if member, err := h.memberService.GetMember(ctx, conv.ID, userID); err == nil {
			role = member.Role
		}
	}
	canManage := role == "owner" || role == "admin"
	canDissolve := role == "owner" && !application.IsCircleBoundConversation(conv)
	return map[string]any{
		"conversationId":     conv.ID,
		"title":              conv.Title,
		"avatarUrl":          h.resolveConversationAvatarURL(ctx, conv),
		"groupAvatarVersion": conv.GroupAvatarVersion,
		"circleId":           conv.CircleId,
		"circleGroupId":      conv.CircleGroupId,
		"entityId":           conv.EntityId,
		"sourceEntityTitle":  conv.EntityId,
		"sourceCircleTitle":  conv.CircleId,
		"memberCount":        conv.MemberCount,
		"announcement":       "",
		"capabilities":       []string{"album", "file", "event", "member"},
		"originType":         conv.OriginType,
		"bindingType":        conv.BindingType,
		"lifecyclePolicy":    conv.LifecyclePolicy,
		"canManageMembers":   canManage,
		"canDissolve":        canDissolve,
	}
}

func normalizeMessageHomeFilter(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "unread", "group", "direct", "notification":
		return strings.ToLower(strings.TrimSpace(value))
	default:
		return "all"
	}
}

func messageHomeMatchesFilter(item application.InboxItem, filter string) bool {
	switch filter {
	case "unread":
		return item.UserState.UnreadCount > 0
	case "group":
		return item.Conversation.Type == "group"
	case "direct":
		return item.Conversation.Type == "direct" || item.Conversation.Type == "encrypted"
	case "notification":
		return false
	default:
		return true
	}
}

func normalizeContactHomeFilter(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "mutual", "circle", "group":
		return strings.ToLower(strings.TrimSpace(value))
	default:
		return "all"
	}
}

func firstTwoNonEmpty(values ...string) []string {
	out := make([]string, 0, 2)
	seen := map[string]struct{}{}
	for _, value := range values {
		trimmed := strings.TrimSpace(value)
		if trimmed == "" {
			continue
		}
		if _, ok := seen[trimmed]; ok {
			continue
		}
		seen[trimmed] = struct{}{}
		out = append(out, trimmed)
		if len(out) == 2 {
			break
		}
	}
	return out
}

func joinNonEmpty(sep string, values ...string) string {
	out := make([]string, 0, len(values))
	for _, value := range values {
		trimmed := strings.TrimSpace(value)
		if trimmed != "" {
			out = append(out, trimmed)
		}
	}
	return strings.Join(out, sep)
}

func stringFromMap(m map[string]any, key string) string {
	if m == nil {
		return ""
	}
	value, ok := m[key]
	if !ok || value == nil {
		return ""
	}
	switch typed := value.(type) {
	case string:
		return strings.TrimSpace(typed)
	case []byte:
		return strings.TrimSpace(string(typed))
	default:
		return strings.TrimSpace(fmt.Sprint(value))
	}
}

func firstStringFromMap(m map[string]any, keys ...string) string {
	for _, key := range keys {
		value := stringFromMap(m, key)
		if value != "" {
			return value
		}
	}
	return ""
}

func boolFromMap(m map[string]any, key string) bool {
	if m == nil {
		return false
	}
	value, ok := m[key]
	if !ok {
		return false
	}
	result, ok := value.(bool)
	return ok && result
}

func parseOptionalRFC3339(value string) *time.Time {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return nil
	}
	parsed, err := time.Parse(time.RFC3339, trimmed)
	if err != nil {
		return nil
	}
	return &parsed
}

func (h *ChatHandler) conversationToWire(ctx context.Context, conv model.Conversation) map[string]any {
	avatarURL := h.resolveConversationAvatarURL(ctx, conv)
	return map[string]any{
		"id":                    conv.ID,
		"_id":                   conv.ID,
		"conversationId":        conv.ID,
		"type":                  conv.Type,
		"title":                 conv.Title,
		"avatarUrl":             avatarURL,
		"groupAvatarVersion":    conv.GroupAvatarVersion,
		"creatorId":             conv.CreatorId,
		"circleId":              conv.CircleId,
		"circleGroupId":         conv.CircleGroupId,
		"entityId":              conv.EntityId,
		"originType":            conv.OriginType,
		"bindingType":           conv.BindingType,
		"lifecyclePolicy":       conv.LifecyclePolicy,
		"maxSeq":                conv.MaxSeq,
		"memberCount":           conv.MemberCount,
		"membersRosterRevision": conv.MembersRosterRevision,
		"maxGroupSize":          conv.MaxGroupSize,
		"receiptEnabled":        conv.ReceiptEnabled,
		"lastMessageId":         conv.LastMessageId,
		"lastMessagePreview":    conv.LastMessagePreview,
		"lastMessageTime":       conv.LastMessageTime,
		"messageCount":          conv.MessageCount,
		"status":                conv.Status,
		"createdAt":             conv.CreatedAt,
		"updatedAt":             conv.UpdatedAt,
	}
}

func (h *ChatHandler) resolveConversationAvatarURL(ctx context.Context, conv model.Conversation) string {
	if conv.Type != "group" {
		return application.ResolveConversationAvatarURL(conv)
	}
	if application.ResolveGroupAvatarURL(conv) != "" {
		return application.ResolveConversationAvatarURL(conv)
	}
	if h == nil || h.memberService == nil {
		return application.ResolveConversationAvatarURL(conv)
	}
	members, err := h.memberService.ListMembers(ctx, application.ListMembersRequest{
		ConversationId: conv.ID,
		Limit:          200,
		Sort:           "joined_asc",
	})
	if err != nil {
		return application.ResolveConversationAvatarURL(conv)
	}
	return application.ResolveConversationAvatarURLWithMembers(conv, members)
}

func messageToWire(msg model.Message) map[string]any {
	wire := map[string]any{
		"id":                 msg.ID,
		"_id":                msg.ID,
		"conversationId":     msg.ConversationId,
		"seq":                msg.Seq,
		"clientMsgId":        msg.ClientMsgId,
		"senderId":           msg.SenderId,
		"senderSubAccountId": msg.SenderId,
		"type":               msg.Type,
		"content":            msg.Content,
		"mediaUrl":           msg.MediaUrl,
		"media":              msg.Media,
		"cardPayload":        msg.CardPayload,
		"replyToMessageId":   msg.ReplyToMessageId,
		"mentions":           msg.Mentions,
		"status":             msg.Status,
		"metadata":           msg.Metadata,
		"timestamp":          msg.Timestamp,
	}
	if msg.RecalledAt != nil {
		wire["recalledAt"] = msg.RecalledAt
	}
	if msg.Metadata != nil {
		if displayName, ok := msg.Metadata["senderDisplayNameSnapshot"]; ok {
			wire["senderDisplayNameSnapshot"] = displayName
		}
		if avatarUrl, ok := msg.Metadata["senderAvatarUrlSnapshot"]; ok {
			wire["senderAvatarUrlSnapshot"] = avatarUrl
		}
		if contextVersion, ok := msg.Metadata["personaContextVersion"]; ok {
			wire["personaContextVersion"] = contextVersion
		}
	}
	return wire
}

func writeHTTPError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

func newNotFound(entity, id string) *rterr.AppError {
	reason := "not_found"
	if entity == "会话" {
		reason = "conversation_not_found"
	}
	return rterr.NewAppError(
		rterr.NewCode(rterr.ModuleChat, rterr.KindUser, reason),
		entity+"不存在",
		entity+" not found: "+id,
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
