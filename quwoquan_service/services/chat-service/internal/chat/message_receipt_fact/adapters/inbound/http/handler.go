package http

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	receiptmodel "quwoquan_service/services/chat-service/internal/chat/message_receipt_fact/domain/model"
)

type Query interface {
	GetReceipts(context.Context, string, string, string) ([]receiptmodel.Fact, error)
}

type Handler struct {
	query Query
}

func NewHandler(query Query) *Handler {
	if query == nil {
		panic("message receipt fact query is required")
	}
	return &Handler{query: query}
}

func (handler *Handler) GetReceipts(w http.ResponseWriter, request *http.Request) {
	conversationID := extractPathParam(
		request.URL.Path,
		"/chat/conversations/{conversationId}/messages/{messageId}/receipts",
		"conversationId",
	)
	messageID := extractPathParam(
		request.URL.Path,
		"/chat/conversations/{conversationId}/messages/{messageId}/receipts",
		"messageId",
	)
	receipts, err := handler.query.GetReceipts(
		request.Context(), conversationID, messageID, resolvePersonaID(request),
	)
	if err != nil {
		rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(request))
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(map[string]any{"items": receipts})
}

func resolvePersonaID(request *http.Request) string {
	if principal, ok := rtauth.PrincipalFromContext(request.Context()); ok {
		return strings.TrimSpace(principal.Actor.PersonaID)
	}
	return strings.TrimSpace(request.Header.Get("X-Client-Persona-Id"))
}

func extractPathParam(path, template, name string) string {
	pathParts := strings.Split(strings.Trim(path, "/"), "/")
	templateParts := strings.Split(strings.Trim(template, "/"), "/")
	if len(pathParts) != len(templateParts) {
		return ""
	}
	needle := "{" + name + "}"
	for index, part := range templateParts {
		if part == needle {
			return strings.TrimSpace(pathParts[index])
		}
	}
	return ""
}
