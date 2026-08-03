package http

import (
	"net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
)

func (handler *ChatHandler) handleProjectGatheringConversation(
	writer http.ResponseWriter,
	request *http.Request,
) {
	var body struct {
		SourceEventID  string `json:"sourceEventId"`
		OwnerPersonaID string `json:"ownerPersonaId"`
		Title          string `json:"title"`
		MaxGroupSize   int    `json:"maxGroupSize"`
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
			OwnerPersonaID: body.OwnerPersonaID, Title: body.Title,
			MaxGroupSize: body.MaxGroupSize,
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
