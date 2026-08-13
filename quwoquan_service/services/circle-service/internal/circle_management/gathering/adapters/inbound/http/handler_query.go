package http

import (
	"encoding/json"
	"log/slog"
	stdhttp "net/http"
	"strconv"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	app "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
)

// QueryHandler owns the canonical named Gathering query slices.
type QueryHandler struct {
	queries *app.GatheringQueryFacade
}

func NewQueryHandler(queries *app.GatheringQueryFacade) *QueryHandler {
	if queries == nil {
		panic("Gathering HTTP QueryHandler requires typed query facade")
	}
	return &QueryHandler{queries: queries}
}

func (handler *QueryHandler) Register(mux *stdhttp.ServeMux) {
	if mux == nil {
		panic("Gathering HTTP QueryHandler requires ServeMux")
	}
	mux.HandleFunc("GET /gatherings/mine", handler.listMine)
	mux.HandleFunc("GET /gatherings/by-host", handler.listByHost)
	mux.HandleFunc("GET /gatherings/by-source", handler.listBySource)
	mux.HandleFunc("GET /public/gatherings/{gatheringId}", handler.getPublicGathering)
	mux.HandleFunc("GET /gatherings/{gatheringId}/applications", handler.listApplications)
	mux.HandleFunc("GET /gatherings/{gatheringId}/roster", handler.listRoster)
	mux.HandleFunc("GET /gatherings/{gatheringId}", handler.getGathering)
	mux.HandleFunc(
		"GET /internal/circle/gatherings/{gatheringId}/participations/{personaId}",
		handler.getParticipationStatus,
	)
}

// getParticipationStatus 只对 service principal 开放（visibility=internal）：
// Content 在接受 post.gatheringRef 回流引用前经此确认作者当前参与状态，fail-closed。
func (handler *QueryHandler) getParticipationStatus(
	writer stdhttp.ResponseWriter,
	request *stdhttp.Request,
) {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if !ok || !strings.HasPrefix(principal.Subject, "service:") {
		writeQueryError(
			writer,
			request,
			gatheringerrors.AppErrorFromGatheringPermissionDenied(
				"Gathering participation status is service-internal",
			),
		)
		return
	}
	result, err := handler.queries.GetParticipationStatus(
		request.Context(),
		app.ParticipationStatusQuery{
			GatheringID: request.PathValue("gatheringId"),
			PersonaID:   request.PathValue("personaId"),
		},
	)
	if err != nil {
		writeQueryError(writer, request, err)
		return
	}
	writeQueryJSON(writer, stdhttp.StatusOK, result)
}

func (handler *QueryHandler) getGathering(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	result, err := handler.queries.GetGathering(request.Context(), app.GatheringIDQuery{
		GatheringID: request.PathValue("gatheringId"),
	})
	if err != nil {
		writeQueryError(writer, request, err)
		return
	}
	writeQueryJSON(writer, stdhttp.StatusOK, result)
}

func (handler *QueryHandler) getPublicGathering(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	result, err := handler.queries.GetPublicGathering(request.Context(), app.GatheringIDQuery{
		GatheringID: request.PathValue("gatheringId"),
	})
	if err != nil {
		writeQueryError(writer, request, err)
		return
	}
	writeQueryJSON(writer, stdhttp.StatusOK, result)
}

func (handler *QueryHandler) listMine(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	limit, err := queryLimit(request)
	if err != nil {
		writeQueryError(writer, request, err)
		return
	}
	result, err := handler.queries.ListMyHostedGatherings(
		request.Context(),
		app.ListMineQuery{
			Cursor: request.URL.Query().Get("cursor"),
			Limit:  limit,
		},
	)
	if err != nil {
		writeQueryError(writer, request, err)
		return
	}
	writeQueryJSON(writer, stdhttp.StatusOK, result)
}

func (handler *QueryHandler) listByHost(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	limit, err := queryLimit(request)
	if err != nil {
		writeQueryError(writer, request, err)
		return
	}
	values := request.URL.Query()
	result, err := handler.queries.ListByHost(request.Context(), app.ListByHostQuery{
		Host: app.HostRef{
			SubjectKind: contract.GatheringHostSubjectKind(
				strings.TrimSpace(values.Get("hostSubjectKind")),
			),
			SubjectID: strings.TrimSpace(values.Get("hostSubjectId")),
		},
		Cursor: values.Get("cursor"),
		Limit:  limit,
	})
	if err != nil {
		writeQueryError(writer, request, err)
		return
	}
	writeQueryJSON(writer, stdhttp.StatusOK, result)
}

func (handler *QueryHandler) listBySource(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	limit, err := queryLimit(request)
	if err != nil {
		writeQueryError(writer, request, err)
		return
	}
	values := request.URL.Query()
	result, err := handler.queries.ListBySource(request.Context(), app.ListBySourceQuery{
		Source: app.CanonicalObjectRef{
			ObjectTypeRef: strings.TrimSpace(values.Get("sourceObjectTypeRef")),
			ObjectID:      strings.TrimSpace(values.Get("sourceObjectId")),
		},
		Cursor: values.Get("cursor"),
		Limit:  limit,
	})
	if err != nil {
		writeQueryError(writer, request, err)
		return
	}
	writeQueryJSON(writer, stdhttp.StatusOK, result)
}

func (handler *QueryHandler) listApplications(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	limit, err := queryLimit(request)
	if err != nil {
		writeQueryError(writer, request, err)
		return
	}
	result, err := handler.queries.ListApplications(request.Context(), app.GatheringPageQuery{
		GatheringID: request.PathValue("gatheringId"),
		Cursor:      request.URL.Query().Get("cursor"),
		Limit:       limit,
	})
	if err != nil {
		writeQueryError(writer, request, err)
		return
	}
	writeQueryJSON(writer, stdhttp.StatusOK, result)
}

func (handler *QueryHandler) listRoster(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	limit, err := queryLimit(request)
	if err != nil {
		writeQueryError(writer, request, err)
		return
	}
	result, err := handler.queries.ListRoster(request.Context(), app.GatheringPageQuery{
		GatheringID: request.PathValue("gatheringId"),
		Cursor:      request.URL.Query().Get("cursor"),
		Limit:       limit,
	})
	if err != nil {
		writeQueryError(writer, request, err)
		return
	}
	writeQueryJSON(writer, stdhttp.StatusOK, result)
}

func queryLimit(request *stdhttp.Request) (int, error) {
	raw := strings.TrimSpace(request.URL.Query().Get("limit"))
	if raw == "" {
		return 0, nil
	}
	value, err := strconv.Atoi(raw)
	if err != nil || value <= 0 {
		return 0, rterr.NewInvalidArgument(
			rterr.ModuleCircle,
			"分页参数无效",
			"Gathering query limit must be a positive integer",
		)
	}
	return value, nil
}

type queryResponse interface {
	app.PrivateDetail |
		app.PublicDetail |
		app.ByHostPage |
		app.BySourcePage |
		app.ApplicationInboxPage |
		app.RosterPage |
		app.ParticipationStatus
}

func writeQueryJSON[Response queryResponse](
	writer stdhttp.ResponseWriter,
	status int,
	value Response,
) {
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(status)
	if err := json.NewEncoder(writer).Encode(value); err != nil {
		slog.Default().Warn("Gathering typed query response encode failed", "error", err)
	}
}

func writeQueryError(writer stdhttp.ResponseWriter, request *stdhttp.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
