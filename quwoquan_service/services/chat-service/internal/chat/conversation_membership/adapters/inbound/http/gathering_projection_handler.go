package http

import (
	"encoding/json"
	"net/http"

	rterr "quwoquan_service/runtime/errors"
	membershipapp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/application"
)

type GatheringProjectionHandler struct {
	facade *membershipapp.GatheringProjectionFacade
}

func NewGatheringProjectionHandler(
	facade *membershipapp.GatheringProjectionFacade,
) *GatheringProjectionHandler {
	if facade == nil {
		panic("Gathering membership projection handler requires facade")
	}
	return &GatheringProjectionHandler{facade: facade}
}

func (handler *GatheringProjectionHandler) Register(mux *http.ServeMux) {
	if mux == nil {
		panic("Gathering membership projection handler requires ServeMux")
	}
	mux.HandleFunc(
		"PUT /internal/chat/gathering-conversations/{gatheringId}/members/{personaId}",
		handler.project,
	)
}

func (handler *GatheringProjectionHandler) project(
	writer http.ResponseWriter,
	request *http.Request,
) {
	var body struct {
		SourceEventID  string `json:"sourceEventId"`
		SourceVersion  int64  `json:"sourceVersion"`
		OwnerPersonaID string `json:"ownerPersonaId"`
		State          string `json:"state"`
	}
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		writeError(writer, request, rterr.NewInvalidArgument(
			rterr.ModuleChat, "相聚成员事实无效", err.Error(),
		))
		return
	}
	result, err := handler.facade.Project(request.Context(), membershipapp.GatheringProjectionCommand{
		SourceEventID: body.SourceEventID, SourceVersion: body.SourceVersion,
		GatheringID: request.PathValue("gatheringId"), PersonaID: request.PathValue("personaId"),
		OwnerPersonaID: body.OwnerPersonaID, State: body.State,
	})
	if err != nil {
		writeError(writer, request, err)
		return
	}
	writeJSON(writer, http.StatusOK, result)
}
