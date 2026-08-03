package http

import (
	stdhttp "net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/httpcodec"
	app "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/domain/model"
)

type Handler struct {
	commands *app.CommandFacade
	queries  *app.QueryFacade
}

func NewHandler(commands *app.CommandFacade, queries *app.QueryFacade) *Handler {
	if commands == nil || queries == nil {
		panic("CircleMembership Handler requires object command and query facades")
	}
	return &Handler{commands: commands, queries: queries}
}

func (handler *Handler) ServeCircleRoute(
	writer stdhttp.ResponseWriter,
	request *stdhttp.Request,
	circleID string,
	rest []string,
) {
	circleID = strings.TrimSpace(circleID)
	if circleID == "" {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求参数无效", "circleId is required"))
		return
	}
	if len(rest) == 0 {
		handler.serveCollection(writer, request, circleID)
		return
	}
	if len(rest) == 1 && rest[0] == "pending" {
		if request.Method != stdhttp.MethodGet {
			writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "pending memberships only accepts GET"))
			return
		}
		result, err := handler.queries.ListPendingCircleMemberships(
			request.Context(), circleID, pageLimit(request), request.URL.Query().Get("cursor"),
		)
		if err != nil {
			writeError(writer, request, err)
			return
		}
		httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_membership")
		return
	}
	if len(rest) == 1 && (strings.HasSuffix(rest[0], ":approve") || strings.HasSuffix(rest[0], ":reject")) {
		handler.serveDecision(writer, request, circleID, rest[0])
		return
	}
	if len(rest) == 1 && rest[0] == "self" {
		handler.serveSelf(writer, request, circleID)
		return
	}
	if len(rest) == 2 && rest[1] == "role" {
		handler.serveRole(writer, request, circleID, strings.TrimSpace(rest[0]))
		return
	}
	writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "unknown CircleMembership command"))
}

func (handler *Handler) ServePersonaCircles(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	if request.Method != stdhttp.MethodGet {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "Persona circles only accepts GET"))
		return
	}
	parts := strings.Split(strings.Trim(strings.TrimPrefix(request.URL.Path, "/personas/"), "/"), "/")
	if len(parts) != 2 || parts[0] == "" || parts[1] != "circles" {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "expected /personas/{personaId}/circles"))
		return
	}
	result, err := handler.queries.ListPersonaCircles(
		request.Context(), parts[0], request.URL.Query().Get("query"),
		pageLimit(request), request.URL.Query().Get("cursor"),
	)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_membership")
}

func (handler *Handler) serveCollection(writer stdhttp.ResponseWriter, request *stdhttp.Request, circleID string) {
	switch request.Method {
	case stdhttp.MethodPost:
		result, err := handler.commands.Join(request.Context(), circleID)
		if err != nil {
			writeError(writer, request, err)
			return
		}
		httpcodec.WriteJSON(writer, stdhttp.StatusCreated, result, "circle_membership")
	case stdhttp.MethodGet:
		result, err := handler.queries.ListCircleMemberships(
			request.Context(), circleID, pageLimit(request), request.URL.Query().Get("cursor"),
		)
		if err != nil {
			writeError(writer, request, err)
			return
		}
		httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_membership")
	default:
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "memberships accepts POST or GET"))
	}
}

func (handler *Handler) serveDecision(writer stdhttp.ResponseWriter, request *stdhttp.Request, circleID, raw string) {
	if request.Method != stdhttp.MethodPost {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "membership approval only accepts POST"))
		return
	}
	target, kind := raw, "approve"
	if strings.HasSuffix(target, ":approve") {
		target = strings.TrimSuffix(target, ":approve")
	} else {
		target, kind = strings.TrimSuffix(target, ":reject"), "reject"
	}
	command := app.DecideCommand{CircleID: circleID, TargetPersonaID: strings.TrimSpace(target)}
	var (
		result app.CommandResult
		err    error
	)
	if kind == "approve" {
		result, err = handler.commands.Approve(request.Context(), command)
	} else {
		result, err = handler.commands.Reject(request.Context(), command)
	}
	if err != nil {
		writeError(writer, request, err)
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_membership")
}

func (handler *Handler) serveSelf(writer stdhttp.ResponseWriter, request *stdhttp.Request, circleID string) {
	if request.Method == stdhttp.MethodGet {
		result, err := handler.queries.GetMyCircleMembership(request.Context(), circleID)
		if err != nil {
			writeError(writer, request, err)
			return
		}
		httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_membership")
		return
	}
	if request.Method != stdhttp.MethodDelete {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "self membership accepts GET or DELETE"))
		return
	}
	result, err := handler.commands.Leave(request.Context(), app.LeaveCommand{CircleID: circleID})
	if err != nil {
		writeError(writer, request, err)
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_membership")
}

func (handler *Handler) serveRole(writer stdhttp.ResponseWriter, request *stdhttp.Request, circleID, targetPersonaID string) {
	if request.Method != stdhttp.MethodPatch {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "membership role only accepts PATCH"))
		return
	}
	var body struct {
		Role string `json:"role"`
	}
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
		return
	}
	result, err := handler.commands.UpdateRole(request.Context(), app.UpdateRoleCommand{
		CircleID: circleID, TargetPersonaID: targetPersonaID, Role: model.CircleMemberRole(body.Role),
	})
	if err != nil {
		writeError(writer, request, err)
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_membership")
}

func pageLimit(request *stdhttp.Request) int {
	limit, _ := strconv.Atoi(request.URL.Query().Get("limit"))
	if limit <= 0 {
		return 20
	}
	if limit > 100 {
		return 100
	}
	return limit
}

func writeError(writer stdhttp.ResponseWriter, request *stdhttp.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
