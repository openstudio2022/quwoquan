package http

import (
	"net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	runtimesync "quwoquan_service/runtime/sync"
	"quwoquan_service/services/chat-service/internal/application"
	"quwoquan_service/services/chat-service/internal/generated"
)

type ChatHandler struct {
	conversationService *application.ConversationService
	messageService      *application.MessageService
	memberService       *application.MemberService
	inboxService        *application.InboxService
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
		ConversationId: convId, ViewerID: resolvePersonaID(r),
		Limit: limit, AfterSeq: afterSeq, BeforeSeq: beforeSeq,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}

	cursor := ""
	if len(msgs) > 0 {
		cursor = msgs[len(msgs)-1].Message.ID
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
		Type                      string                          `json:"type"`
		Content                   string                          `json:"content"`
		MediaAssetID              string                          `json:"mediaAssetId"`
		Card                      *application.MessageCardCommand `json:"card"`
		ReplyToMessageId          string                          `json:"replyToMessageId"`
		Mentions                  []string                        `json:"mentions"`
		ClientMsgId               string                          `json:"clientMsgId"`
		PersonaContextVersion     int64                           `json:"personaContextVersion"`
		SenderDisplayNameSnapshot string                          `json:"senderDisplayNameSnapshot"`
		SenderAvatarUrlSnapshot   string                          `json:"senderAvatarUrlSnapshot"`
	}
	if err := readStrictJSON(r, &body); err != nil {
		writeHTTPError(w, r, generated.AppErrorFromMessageInvalid(err.Error()))
		return
	}

	senderID := resolvePersonaID(r)
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
		Content: body.Content, MediaAssetID: body.MediaAssetID, Card: body.Card,
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

	err := h.messageService.RecallMessage(r.Context(), convId, msgId, resolvePersonaID(r))
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
	if err := readStrictJSON(r, &body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}

	resp, err := h.messageService.SyncMessages(r.Context(), application.SyncMessagesRequest{
		ConversationId: convId, ViewerID: resolvePersonaID(r), LastSeq: body.LastSeq, Limit: body.Limit,
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
		ConversationId: convId, MessageId: msgId, UserId: resolvePersonaID(r),
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

	receipts, err := h.messageService.GetReceipts(r.Context(), convId, msgId, resolvePersonaID(r))
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

	err := h.memberService.RemoveAssistant(r.Context(), application.RemoveAssistantRequest{
		ConversationId: convId,
		RemovedBy:      resolveUserID(r),
	})
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
	if filter == "all" || filter == "circle" {
		circles, err := h.memberService.ListContactHomeCircles(r.Context(), userID, limit)
		if err != nil {
			writeHTTPError(w, r, err)
			return
		}
		for _, circle := range circles {
			rows = append(rows, contactHomeCircleRowToWire(circle))
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
			"senderPersonaId":       hit.Message.SenderID,
			"senderDisplayName":     hit.Message.SenderID,
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
