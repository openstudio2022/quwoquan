package http

import (
	stdhttp "net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/httpcodec"
	app "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/domain/model"
)

type Handler struct {
	commands *app.CommandFacade
	queries  *app.QueryFacade
}

func NewHandler(commands *app.CommandFacade, queries *app.QueryFacade) *Handler {
	if commands == nil || queries == nil {
		panic("CircleGroupMembership Handler requires object command and query facades")
	}
	return &Handler{commands: commands, queries: queries}
}

func (handler *Handler) ServeCircleGroupRoute(
	writer stdhttp.ResponseWriter,
	request *stdhttp.Request,
	circleID string,
	groupID string,
	rest []string,
) {
	if len(rest) == 0 {
		handler.serveCollection(writer, request, circleID, groupID)
		return
	}
	if len(rest) == 1 && rest[0] == "self" {
		handler.serveSelf(writer, request, circleID, groupID)
		return
	}
	if len(rest) == 1 {
		handler.serveTarget(writer, request, circleID, groupID, rest[0])
		return
	}
	if len(rest) == 2 && rest[1] == "role" && request.Method == stdhttp.MethodPatch {
		var body struct {
			Role string `json:"role"`
		}
		if err := httpcodec.DecodeStrictJSON(request, &body); err != nil {
			writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
			return
		}
		result, err := handler.commands.UpdateRole(request.Context(), app.TargetCommand{
			CircleID: circleID, GroupID: groupID, TargetPersonaID: strings.TrimSpace(rest[0]),
			Role: model.CircleGroupMembershipRole(body.Role),
		})
		if err != nil {
			writeError(writer, request, err)
			return
		}
		httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_group_membership")
		return
	}
	writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "unknown CircleGroupMembership route"))
}

func (handler *Handler) serveCollection(writer stdhttp.ResponseWriter, request *stdhttp.Request, circleID, groupID string) {
	switch request.Method {
	case stdhttp.MethodPost:
		result, err := handler.commands.Apply(request.Context(), circleID, groupID)
		if err != nil {
			writeError(writer, request, err)
			return
		}
		httpcodec.WriteJSON(writer, stdhttp.StatusCreated, result, "circle_group_membership")
	case stdhttp.MethodGet:
		result, err := handler.queries.List(
			request.Context(), circleID, groupID, request.URL.Query().Get("state"),
			pageLimit(request), request.URL.Query().Get("cursor"),
		)
		if err != nil {
			writeError(writer, request, err)
			return
		}
		httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_group_membership")
	default:
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "group memberships accepts POST or GET"))
	}
}

func (handler *Handler) serveSelf(writer stdhttp.ResponseWriter, request *stdhttp.Request, circleID, groupID string) {
	if request.Method == stdhttp.MethodGet {
		result, err := handler.queries.GetMy(request.Context(), circleID, groupID)
		if err != nil {
			writeError(writer, request, err)
			return
		}
		httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_group_membership")
		return
	}
	if request.Method != stdhttp.MethodDelete {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "self group membership accepts GET or DELETE"))
		return
	}
	result, err := handler.commands.Leave(request.Context(), app.SelfCommand{CircleID: circleID, GroupID: groupID})
	if err != nil {
		writeError(writer, request, err)
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_group_membership")
}

func (handler *Handler) serveTarget(writer stdhttp.ResponseWriter, request *stdhttp.Request, circleID, groupID, raw string) {
	target, kind := strings.TrimSpace(raw), "remove"
	if strings.HasSuffix(target, ":approve") {
		target, kind = strings.TrimSuffix(target, ":approve"), "approve"
	}
	if strings.HasSuffix(target, ":reject") {
		target, kind = strings.TrimSuffix(target, ":reject"), "reject"
	}
	if target == "" {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求参数无效", "personaId is required"))
		return
	}
	if (kind == "remove" && request.Method != stdhttp.MethodDelete) || (kind != "remove" && request.Method != stdhttp.MethodPost) {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "invalid group membership command method"))
		return
	}
	command := app.TargetCommand{CircleID: circleID, GroupID: groupID, TargetPersonaID: target}
	var (
		result app.CommandResult
		err    error
	)
	switch kind {
	case "approve":
		result, err = handler.commands.Approve(request.Context(), command)
	case "reject":
		result, err = handler.commands.Reject(request.Context(), command)
	default:
		result, err = handler.commands.Remove(request.Context(), command)
	}
	if err != nil {
		writeError(writer, request, err)
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_group_membership")
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
