package http

import (
	"net/http"
	"strconv"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/httpcodec"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	profileinteractiongenerated "quwoquan_service/services/content-service/generated/content/profile_interaction_activity_view"
	profileinteractionapp "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/application"
)

type Handler struct {
	facade profileinteractionapp.ActivityQueryFacade
}

func NewHandler(facade profileinteractionapp.ActivityQueryFacade) *Handler {
	if facade == nil {
		panic("ProfileInteractionActivityView HTTP handler requires query facade")
	}
	return &Handler{facade: facade}
}

func (handler *Handler) ListReceived(writer http.ResponseWriter, request *http.Request) {
	handler.list(writer, request, "received")
}

func (handler *Handler) ListSent(writer http.ResponseWriter, request *http.Request) {
	handler.list(writer, request, "sent")
}

func (handler *Handler) list(
	writer http.ResponseWriter,
	request *http.Request,
	direction string,
) {
	personaID := strings.TrimSpace(request.PathValue("personaId"))
	if personaID == "" {
		writeHTTPError(writer, request, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"互动身份不能为空",
			"missing personaId",
		))
		return
	}
	limit := 20
	if raw := strings.TrimSpace(request.URL.Query().Get("limit")); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed <= 0 {
			writeHTTPError(writer, request, contentgenerated.AppErrorFromInvalidArgument(
				"profile interaction limit must be positive",
			))
			return
		}
		limit = parsed
	}
	page, err := handler.facade.ListActivities(
		request.Context(),
		profileinteractionapp.ActivityPageQuery{
			OwnerPersonaID:  personaID,
			ViewerPersonaID: operationActorID(request),
			Direction:       direction,
			ActivityType:    strings.TrimSpace(request.URL.Query().Get("type")),
			Cursor:          strings.TrimSpace(request.URL.Query().Get("cursor")),
			Limit:           limit,
		},
	)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	httpcodec.WriteJSON(writer, http.StatusOK, page, "profile_interaction_activity_view")
}

func operationActorID(request *http.Request) string {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if !ok {
		return ""
	}
	actorID, _ := principal.Actor.BusinessActorID()
	return actorID
}

func writeHTTPError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}

var _ = profileinteractiongenerated.AppErrorFromInteractionReadModelUnavailable
