package http

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	inboxapp "quwoquan_service/services/chat-service/internal/chat/chat_inbox_view/application"
)

type Handler struct{ reader *inboxapp.Reader }

func NewHandler(store inboxapp.Store) *Handler {
	return &Handler{reader: inboxapp.NewReader(store)}
}

func (handler *Handler) Register(mux *http.ServeMux) {
	if mux == nil {
		panic("ChatInboxView route mux is required")
	}
	mux.HandleFunc("GET /chat/inbox", handler.list)
}

func (handler *Handler) list(writer http.ResponseWriter, request *http.Request) {
	limit := 50
	if raw := strings.TrimSpace(request.URL.Query().Get("limit")); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed <= 0 {
			writeError(writer, request, rterr.NewInvalidArgument(
				rterr.ModuleChat, "收件箱分页参数无效", "limit must be positive",
			))
			return
		}
		limit = parsed
	}
	page, err := handler.reader.List(
		request.Context(), personaID(request), limit, request.URL.Query().Get("cursor"),
	)
	if err != nil {
		if errors.Is(err, inboxapp.ErrInvalidCursor) {
			err = rterr.NewInvalidArgument(
				rterr.ModuleChat, "收件箱游标无效", "cursor must be the current opaque keyset token",
			)
		}
		writeError(writer, request, err)
		return
	}
	items := make([]map[string]any, 0, len(page.Items))
	for _, item := range page.Items {
		items = append(items, map[string]any{
			"id": item.ConversationID, "conversationId": item.ConversationID,
			"type": item.Type, "title": item.Title, "avatarUrl": item.AvatarURL,
			"groupAvatarVersion": item.GroupAvatarVersion,
			"lastMessagePreview": item.LastMessagePreview,
			"lastMessageType":    item.LastMessageType,
			"lastMessageTime":    nullableTime(item.LastMessageTime), "lastSeq": item.LastSeq,
			"unreadCount": item.UnreadCount, "mentionUnreadCount": item.MentionUnreadCount,
			"muted": item.Muted, "pinned": item.Pinned, "circleId": item.CircleID,
		})
	}
	response := map[string]any{"items": items}
	if page.NextCursor != "" {
		response["nextCursor"] = page.NextCursor
	}
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	_ = json.NewEncoder(writer).Encode(response)
}

func personaID(request *http.Request) string {
	if principal, ok := rtauth.PrincipalFromContext(request.Context()); ok {
		return strings.TrimSpace(principal.Actor.PersonaID)
	}
	return strings.TrimSpace(request.Header.Get("X-Client-Persona-Id"))
}

func nullableTime(value time.Time) any {
	if value.IsZero() {
		return nil
	}
	return value
}

func writeError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
