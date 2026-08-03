package http

import (
	"encoding/json"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	userstateapp "quwoquan_service/services/chat-service/internal/chat/conversation_user_state/application"
)

type Handler struct {
	useCases *userstateapp.UseCases
}

func NewHandler(reads userstateapp.ReadMarker, settings userstateapp.SettingsUpdater) *Handler {
	return &Handler{useCases: userstateapp.NewUseCases(reads, settings)}
}

func (handler *Handler) Register(mux *http.ServeMux) {
	if mux == nil {
		panic("conversation user-state route mux is required")
	}
	mux.HandleFunc(
		"POST /chat/conversations/{conversationId}/messages/{messageId}/read",
		handler.markAsRead,
	)
	mux.HandleFunc(
		"PATCH /chat/conversations/{conversationId}/settings",
		handler.updateSettings,
	)
}

func (handler *Handler) markAsRead(writer http.ResponseWriter, request *http.Request) {
	err := handler.useCases.MarkAsRead(request.Context(), userstateapp.MarkAsReadRequest{
		ConversationId: request.PathValue("conversationId"),
		MessageId:      request.PathValue("messageId"),
		UserId:         personaID(request),
	})
	if err != nil {
		writeError(writer, request, err)
		return
	}
	writeAck(writer)
}

func (handler *Handler) updateSettings(writer http.ResponseWriter, request *http.Request) {
	var body struct {
		Muted  *bool `json:"muted"`
		Pinned *bool `json:"pinned"`
	}
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		writeError(
			writer,
			request,
			rterr.NewInvalidArgument(rterr.ModuleChat, "会话设置请求无效", err.Error()),
		)
		return
	}
	err := handler.useCases.UpdateSettings(request.Context(), userstateapp.UpdateSettingsRequest{
		UserId:         personaID(request),
		ConversationId: request.PathValue("conversationId"),
		Muted:          body.Muted,
		Pinned:         body.Pinned,
	})
	if err != nil {
		writeError(writer, request, err)
		return
	}
	writeAck(writer)
}

func personaID(request *http.Request) string {
	if principal, ok := rtauth.PrincipalFromContext(request.Context()); ok {
		return strings.TrimSpace(principal.Actor.PersonaID)
	}
	return strings.TrimSpace(request.Header.Get("X-Client-Persona-Id"))
}

func writeAck(writer http.ResponseWriter) {
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(http.StatusOK)
	_, _ = writer.Write([]byte(`{"status":"ok"}`))
}

func writeError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
