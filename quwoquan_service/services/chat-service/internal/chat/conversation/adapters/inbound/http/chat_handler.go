package http

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	runtimesync "quwoquan_service/runtime/sync"
	"quwoquan_service/services/chat-service/generated/chat/conversation"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
	conversationmodel "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
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
	h.RegisterRoutes(mux)
	return mux
}

// RegisterRoutes composes Conversation-owned routes into a service-level mux.
// Object-specific adapters are registered on the same mux so Go's route
// specificity selects their canonical path before this adapter's final guard.
func (h *ChatHandler) RegisterRoutes(mux *http.ServeMux) {
	if mux == nil {
		panic("chat route mux is required")
	}
	mux.HandleFunc("/healthz", h.handleHealthz)
	mux.HandleFunc("POST /user/sync", h.handlePullUserSync)
	mux.HandleFunc("PATCH /chat/conversations/{conversationId}", h.handleUpdateConversationTitle)
	mux.HandleFunc("GET /chat/conversations/timestamps", h.handleListConversationTimestamps)
	mux.HandleFunc("POST /chat/conversations/batch", h.handleBatchGetConversations)
	mux.HandleFunc("GET /chat/message-home", h.handleListMessageHome)
	mux.HandleFunc("GET /chat/contact-home", h.handleListContactHome)
	mux.HandleFunc("GET /chat/groups/{conversationId}/home", h.handleGetGroupHome)
	mux.HandleFunc(
		"GET /chat/gathering-conversations/{conversationId}/board",
		h.handleGetGatheringChatBoard,
	)
	mux.HandleFunc("DELETE /chat/conversations/{conversationId}", h.handleDissolveConversation)
	RegisterGeneratedRoutes(mux, h)
}

// InternalRoutes exposes only the service-to-service conversation boundary.
// It is mounted separately from public ContractGraph routes so the generated
// public-operation guard cannot accidentally treat it as an unregistered API.
// Its handlers verify a delegated user-service credential themselves.
func (h *ChatHandler) InternalRoutes() http.Handler {
	mux := http.NewServeMux()
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
			generated.AppErrorFromInternalError("chat user sync service is not configured"),
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
	userId := resolvePersonaID(r)
	cursor := r.URL.Query().Get("cursor")
	limit := queryInt(r, "limit", 20)

	page, err := h.conversationService.ListConversationPage(r.Context(), application.ListConversationsRequest{
		UserId: userId, Cursor: cursor, Limit: limit,
	})
	if err != nil {
		if errors.Is(err, conversationmodel.ErrInvalidInboxCursor) {
			writeHTTPError(w, r, rterr.NewInvalidArgument(
				rterr.ModuleChat,
				"invalid conversation cursor",
				"conversation cursor must be an opaque keyset token",
			))
			return
		}
		writeHTTPError(w, r, err)
		return
	}

	response := map[string]any{
		"items": h.flattenConversations(r.Context(), page.Items),
	}
	if page.NextCursor != "" {
		response["nextCursor"] = page.NextCursor
	}
	writeJSON(w, http.StatusOK, response)
}

func (h *ChatHandler) handleCreateConversation(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Type             string          `json:"type"`
		Title            string          `json:"title"`
		MaxGroupSize     int             `json:"maxGroupSize"`
		InitialMemberIds []string        `json:"initialMemberIds"`
		CircleID         json.RawMessage `json:"circleId"`
		CircleGroupID    json.RawMessage `json:"circleGroupId"`
		GatheringID      json.RawMessage `json:"gatheringId"`
		EntityID         json.RawMessage `json:"entityId"`
		OriginType       json.RawMessage `json:"originType"`
		BindingType      json.RawMessage `json:"bindingType"`
		LifecyclePolicy  json.RawMessage `json:"lifecyclePolicy"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}
	if len(body.CircleID) != 0 ||
		len(body.CircleGroupID) != 0 ||
		len(body.GatheringID) != 0 ||
		len(body.EntityID) != 0 ||
		len(body.OriginType) != 0 ||
		len(body.BindingType) != 0 ||
		len(body.LifecyclePolicy) != 0 {
		writeHTTPError(
			w,
			r,
			generated.AppErrorFromSourceManagedBindingWriteForbidden(
				"public CreateConversation must not submit source binding fields",
			),
		)
		return
	}

	conv, err := h.conversationService.CreateConversation(r.Context(), application.CreateConversationRequest{
		Type: body.Type, Title: body.Title, MaxGroupSize: body.MaxGroupSize,
		CreatorId: resolvePersonaID(r), InitialMemberIds: body.InitialMemberIds,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, h.conversationToWire(r.Context(), *conv))
}

func (h *ChatHandler) handleGetConversation(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/chat/conversations/{conversationId}", "conversationId")
	conv, err := h.conversationService.GetConversation(r.Context(), convId)
	if err != nil {
		writeHTTPError(w, r, newNotFound("会话", convId))
		return
	}
	writeJSON(w, http.StatusOK, h.conversationToWire(r.Context(), *conv))
}

func (h *ChatHandler) handleGetGatheringChatBoard(w http.ResponseWriter, r *http.Request) {
	conversationID := extractPathParam(
		r.URL.Path,
		"/chat/gathering-conversations/{conversationId}/board",
		"conversationId",
	)
	board, err := h.conversationService.GetGatheringChatBoard(
		r.Context(),
		conversationID,
		resolvePersonaID(r),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, board)
}

func (h *ChatHandler) handleUpdateConversationTitle(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/chat/conversations/{conversationId}", "conversationId")
	var body struct {
		Title string `json:"title"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}
	conv, err := h.conversationService.UpdateConversationTitle(r.Context(), application.UpdateConversationTitleRequest{
		ConversationId: convId,
		OperatorId:     resolvePersonaID(r),
		Title:          body.Title,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, h.conversationToWire(r.Context(), *conv))
}

func (h *ChatHandler) handleDissolveConversation(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/chat/conversations/{conversationId}", "conversationId")
	err := h.conversationService.DissolveConversation(r.Context(), application.DissolveConversationRequest{
		ConversationId: convId,
		OperatorId:     resolvePersonaID(r),
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *ChatHandler) handleUpdateAnnouncement(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/chat/conversations/{conversationId}/announcement", "conversationId")
	var body struct {
		Announcement string `json:"announcement"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}
	conv, err := h.conversationService.UpdateAnnouncement(r.Context(), application.UpdateAnnouncementRequest{
		ConversationId: convId,
		OperatorId:     resolvePersonaID(r),
		Announcement:   body.Announcement,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, h.conversationToWire(r.Context(), *conv))
}

func (h *ChatHandler) handleUpdateGroupGovernanceSettings(w http.ResponseWriter, r *http.Request) {
	convId := extractPathParam(r.URL.Path, "/chat/conversations/{conversationId}/governance", "conversationId")
	var body struct {
		NameEditableByAdminOnly *bool `json:"nameEditableByAdminOnly"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}
	conv, err := h.conversationService.UpdateGroupGovernanceSettings(
		r.Context(),
		application.UpdateGroupGovernanceSettingsRequest{
			ConversationId:          convId,
			OperatorId:              resolvePersonaID(r),
			NameEditableByAdminOnly: body.NameEditableByAdminOnly,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, h.conversationToWire(r.Context(), *conv))
}

func (h *ChatHandler) handleListConversationTimestamps(w http.ResponseWriter, r *http.Request) {
	userId := resolvePersonaID(r)
	items, err := h.inboxService.ListInbox(r.Context(), application.ListInboxRequest{
		UserId: userId,
		Limit:  conversationTimestampPageLimit,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	rows := make([]map[string]any, 0, len(items))
	for _, item := range items {
		rows = append(rows, map[string]any{
			"conversationId":     item.Conversation.ID,
			"type":               item.Conversation.Type,
			"updatedAt":          item.Conversation.UpdatedAt.UTC().Format(time.RFC3339Nano),
			"settingsUpdatedAt":  item.UserState.UpdatedAt.UTC().Format(time.RFC3339Nano),
			"lastMessageAt":      formatOptionalTime(item.Conversation.LastMessageTime),
			"lastMessageTime":    formatOptionalTime(item.Conversation.LastMessageTime),
			"lastMessagePreview": item.Conversation.LastMessagePreview,
			"unreadCount":        item.UserState.UnreadCount,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": rows})
}

func (h *ChatHandler) handleBatchGetConversations(w http.ResponseWriter, r *http.Request) {
	userId := resolvePersonaID(r)
	var body struct {
		Ids []string `json:"ids"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "invalid body", err.Error()))
		return
	}
	if len(body.Ids) > batchGetConversationsLimit {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleChat,
			"批量查询数量超过上限",
			"batch conversation lookup exceeds limit",
		))
		return
	}
	items := make([]map[string]any, 0, len(body.Ids))
	seen := make(map[string]struct{}, len(body.Ids))
	for _, rawID := range body.Ids {
		convID := strings.TrimSpace(rawID)
		if convID == "" {
			continue
		}
		if _, dup := seen[convID]; dup {
			continue
		}
		seen[convID] = struct{}{}
		conv, err := h.conversationService.GetConversation(r.Context(), convID)
		if err != nil {
			continue
		}
		// 仅返回请求者为成员的会话（conversation_member ownership）。
		if _, err := h.memberService.GetMember(r.Context(), convID, userId); err != nil {
			continue
		}
		items = append(items, h.conversationToWire(r.Context(), *conv))
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

const (
	conversationTimestampPageLimit = 500
	batchGetConversationsLimit     = 100
)

func (h *ChatHandler) handleListMessageHome(w http.ResponseWriter, r *http.Request) {
	userId := resolvePersonaID(r)
	cursor := r.URL.Query().Get("cursor")
	limit := queryInt(r, "limit", 50)
	filter := normalizeMessageHomeFilter(r.URL.Query().Get("filter"))

	page, err := h.inboxService.ListInboxPage(r.Context(), application.ListInboxRequest{
		UserId: userId, Cursor: cursor, Limit: limit,
	})
	if err != nil {
		if errors.Is(err, conversationmodel.ErrInvalidInboxCursor) {
			writeHTTPError(w, r, rterr.NewInvalidArgument(
				rterr.ModuleChat,
				"invalid message home cursor",
				"message home cursor must be an opaque keyset token",
			))
			return
		}
		writeHTTPError(w, r, err)
		return
	}
	rows := make([]map[string]any, 0, len(page.Items))
	for _, item := range page.Items {
		if !messageHomeMatchesFilter(item, filter) {
			continue
		}
		rows = append(rows, h.messageHomeRowToWire(r.Context(), item))
	}
	response := map[string]any{"items": rows}
	if page.NextCursor != "" {
		response["nextCursor"] = page.NextCursor
	}
	writeJSON(w, http.StatusOK, response)
}

// ── Contacts ─────────────────────────────────────────────────────────────────

func (h *ChatHandler) handleListContacts(w http.ResponseWriter, r *http.Request) {
	cursor := r.URL.Query().Get("cursor")
	limit := queryInt(r, "limit", 20)

	page, err := h.memberService.ListContacts(
		r.Context(),
		resolvePersonaID(r),
		limit,
		cursor,
	)
	if err != nil {
		if errors.Is(err, application.ErrInvalidContactCursor) {
			writeHTTPError(w, r, rterr.NewInvalidArgument(
				rterr.ModuleChat,
				"invalid contacts cursor",
				"contacts cursor must be an opaque keyset token",
			))
			return
		}
		writeHTTPError(w, r, err)
		return
	}
	response := map[string]any{"items": page.Items}
	if page.NextCursor != "" {
		response["nextCursor"] = page.NextCursor
	}
	writeJSON(w, http.StatusOK, response)
}

func (h *ChatHandler) handleListContactHome(w http.ResponseWriter, r *http.Request) {
	cursor := r.URL.Query().Get("cursor")
	limit := queryInt(r, "limit", 50)
	filter := normalizeContactHomeFilter(r.URL.Query().Get("filter"))
	userID := resolvePersonaID(r)

	rows := make([]map[string]any, 0, limit)
	if filter == "all" || filter == "mutual" {
		contacts, err := h.memberService.ListContacts(
			r.Context(),
			userID,
			limit,
			cursor,
		)
		if err != nil {
			writeHTTPError(w, r, err)
			return
		}
		for _, contact := range contacts.Items {
			if filter == "mutual" && stringFromMap(contact, "relationState") != "mutual" {
				continue
			}
			intersections, err := h.memberService.ListContactIntersectionSummaries(
				r.Context(),
				userID,
				stringFromMap(contact, "userId"),
			)
			if err != nil {
				writeHTTPError(w, r, err)
				return
			}
			rows = append(rows, contactHomeUserRowToWire(contact, intersections))
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
	convId := extractPathParam(r.URL.Path, "/chat/groups/{conversationId}/home", "conversationId")
	conv, err := h.conversationService.GetConversation(r.Context(), convId)
	if err != nil {
		writeHTTPError(w, r, newNotFound("会话", convId))
		return
	}
	if conv.Type != "group" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "不是群聊会话", "conversation is not a group"))
		return
	}
	writeJSON(w, http.StatusOK, h.groupHomeToWire(r.Context(), *conv, resolvePersonaID(r)))
}

func (h *ChatHandler) handleListGroupCandidates(w http.ResponseWriter, r *http.Request) {
	limit := queryInt(r, "limit", 100)
	conversationID := strings.TrimSpace(r.URL.Query().Get("conversationId"))
	candidates, err := h.memberService.ListGroupCandidates(
		r.Context(),
		resolvePersonaID(r),
		conversationID,
		limit,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": candidates})
}
