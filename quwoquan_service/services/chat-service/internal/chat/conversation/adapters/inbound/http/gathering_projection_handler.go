package http

import (
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/chat-service/generated/chat/conversation"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
)

func (handler *ChatHandler) handleProjectGatheringConversation(
	writer http.ResponseWriter,
	request *http.Request,
) {
	if !isAuthorizedCircleGatheringProjection(request) {
		writeHTTPError(writer, request, generated.AppErrorFromUnauthorized(
			"Gathering projection requires delegated circle-service authorization",
		))
		return
	}
	var body struct {
		SourceEventID  string `json:"sourceEventId"`
		SourceVersion  int64  `json:"sourceVersion"`
		OwnerPersonaID string `json:"ownerPersonaId"`
		Title          string `json:"title"`
		AccessMode     string `json:"accessMode"`
		PostingPolicy  string `json:"postingPolicy"`
	}
	if err := readJSON(request, &body); err != nil {
		writeHTTPError(writer, request, rterr.NewInvalidArgument(
			rterr.ModuleChat, "相聚会话请求无效", err.Error(),
		))
		return
	}
	gatheringID := strings.TrimSpace(extractPathParam(
		request.URL.Path,
		"/internal/chat/gathering-conversations/{gatheringId}",
		"gatheringId",
	))
	conversation, err := handler.conversationService.ProvisionGatheringConversation(
		request.Context(),
		application.GatheringConversationProvisioningRequest{
			SourceEventID: body.SourceEventID, GatheringID: gatheringID,
			SourceVersion:  body.SourceVersion,
			OwnerPersonaID: body.OwnerPersonaID, Title: body.Title,
			AccessMode: body.AccessMode, PostingPolicy: body.PostingPolicy,
		},
	)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"gatheringId": gatheringID, "conversationId": conversation.ID,
	})
}

func isAuthorizedCircleGatheringProjection(request *http.Request) bool {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if !ok || principal.Subject != "service:circle-service" ||
		!containsGrant(principal.Roles, "service") {
		return false
	}
	return containsGrant(strings.Fields(principal.Scope), "chat.gathering.write")
}
