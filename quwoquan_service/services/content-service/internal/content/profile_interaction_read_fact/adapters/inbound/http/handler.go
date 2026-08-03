package http

import (
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/httpcodec"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	profileinteractiongenerated "quwoquan_service/services/content-service/generated/content/profile_interaction_activity_view"
	readfactapp "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/application"
)

type Handler struct {
	facade readfactapp.ReadFactAppendFacade
}

func NewHandler(facade readfactapp.ReadFactAppendFacade) *Handler {
	if facade == nil {
		panic("ProfileInteractionReadFact HTTP handler requires append facade")
	}
	return &Handler{facade: facade}
}

type appendRequest struct {
	State string `json:"state"`
}

func (handler *Handler) Append(writer http.ResponseWriter, request *http.Request) {
	personaID := strings.TrimSpace(request.PathValue("personaId"))
	activityID := strings.TrimSpace(request.PathValue("interactionId"))
	if personaID == "" || activityID == "" {
		writeHTTPError(writer, request, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"互动标识不能为空",
			"missing personaId or interactionId",
		))
		return
	}
	if err := requireActiveOwner(request, personaID); err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	var body appendRequest
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil {
		writeHTTPError(writer, request, contentgenerated.AppErrorFromInvalidArgument(
			"decode ProfileInteractionReadFact request: "+err.Error(),
		))
		return
	}
	ack, err := handler.facade.AppendReadFact(
		request.Context(),
		readfactapp.AppendReadFactCommand{
			OwnerPersonaID: personaID,
			ActivityID:     activityID,
			State:          strings.TrimSpace(body.State),
		},
	)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	httpcodec.WriteJSON(writer, http.StatusAccepted, ack, "profile_interaction_read_fact")
}

func requireActiveOwner(request *http.Request, personaID string) error {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if !ok || strings.TrimSpace(principal.Subject) == "" {
		return contentgenerated.AppErrorFromUnauthorized(
			"profile interactions require authenticated principal",
		)
	}
	activePersonaID := strings.TrimSpace(principal.Persona)
	if activePersonaID == "" {
		return contentgenerated.AppErrorFromUnauthorized(
			"profile interactions require an active persona",
		)
	}
	if activePersonaID != strings.TrimSpace(personaID) {
		return profileinteractiongenerated.AppErrorFromInteractionOwnerForbidden(
			"requested persona is not the active principal persona",
		)
	}
	return nil
}

func writeHTTPError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
