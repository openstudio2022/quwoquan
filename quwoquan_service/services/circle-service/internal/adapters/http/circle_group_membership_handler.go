package http

import (
	"net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	app "quwoquan_service/services/circle-service/internal/application/circle/circle_group_membership"
	model "quwoquan_service/services/circle-service/internal/domain/circle/circle_group_membership/model"
)

func (handler *CircleHandler) handleGroupMemberships(w http.ResponseWriter, request *http.Request, circleID, groupID string, rest []string) {
	if len(rest) == 0 {
		switch request.Method {
		case http.MethodPost:
			result, err := handler.groupMembershipCommands.Apply(request.Context(), circleID, groupID)
			if err != nil {
				writeHTTPError(w, request, err)
				return
			}
			writeJSON(w, http.StatusCreated, result)
		case http.MethodGet:
			result, err := handler.groupMembershipQueries.List(
				request.Context(), circleID, groupID, request.URL.Query().Get("state"),
				groupPageLimit(request), request.URL.Query().Get("cursor"),
			)
			if err != nil {
				writeHTTPError(w, request, err)
				return
			}
			writeJSON(w, http.StatusOK, result)
		default:
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "group memberships accepts POST or GET"))
		}
		return
	}
	if len(rest) == 1 && rest[0] == "self" {
		if request.Method == http.MethodGet {
			result, err := handler.groupMembershipQueries.GetMy(request.Context(), circleID, groupID)
			if err != nil {
				writeHTTPError(w, request, err)
				return
			}
			writeJSON(w, http.StatusOK, result)
			return
		}
		if request.Method != http.MethodDelete {
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "self group membership accepts GET or DELETE"))
			return
		}
		expectedVersion, err := parseExpectedVersion(request.Header.Get("If-Match"))
		if err != nil {
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求缺少有效版本", err.Error()))
			return
		}
		result, err := handler.groupMembershipCommands.Leave(request.Context(), app.SelfCommand{
			CircleID: circleID, GroupID: groupID, ExpectedVersion: expectedVersion,
		})
		if err != nil {
			writeHTTPError(w, request, err)
			return
		}
		writeJSON(w, http.StatusOK, result)
		return
	}
	if len(rest) == 1 {
		target := strings.TrimSpace(rest[0])
		kind := "remove"
		if strings.HasSuffix(target, ":approve") {
			target, kind = strings.TrimSuffix(target, ":approve"), "approve"
		}
		if strings.HasSuffix(target, ":reject") {
			target, kind = strings.TrimSuffix(target, ":reject"), "reject"
		}
		if target == "" {
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求参数无效", "personaId is required"))
			return
		}
		if (kind == "remove" && request.Method != http.MethodDelete) || (kind != "remove" && request.Method != http.MethodPost) {
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "invalid group membership command method"))
			return
		}
		expectedVersion, err := parseExpectedVersion(request.Header.Get("If-Match"))
		if err != nil {
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求缺少有效版本", err.Error()))
			return
		}
		command := app.TargetCommand{CircleID: circleID, GroupID: groupID, TargetPersonaID: target, ExpectedVersion: expectedVersion}
		var result app.CommandResult
		switch kind {
		case "approve":
			result, err = handler.groupMembershipCommands.Approve(request.Context(), command)
		case "reject":
			result, err = handler.groupMembershipCommands.Reject(request.Context(), command)
		default:
			result, err = handler.groupMembershipCommands.Remove(request.Context(), command)
		}
		if err != nil {
			writeHTTPError(w, request, err)
			return
		}
		writeJSON(w, http.StatusOK, result)
		return
	}
	if len(rest) == 2 && rest[1] == "role" && request.Method == http.MethodPatch {
		expectedVersion, err := parseExpectedVersion(request.Header.Get("If-Match"))
		if err != nil {
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求缺少有效版本", err.Error()))
			return
		}
		var body struct {
			Role string `json:"role"`
		}
		if err := readStrictJSON(request, &body); err != nil {
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
			return
		}
		result, err := handler.groupMembershipCommands.UpdateRole(request.Context(), app.TargetCommand{
			CircleID: circleID, GroupID: groupID, TargetPersonaID: strings.TrimSpace(rest[0]),
			ExpectedVersion: expectedVersion, Role: model.CircleGroupMembershipRole(body.Role),
		})
		if err != nil {
			writeHTTPError(w, request, err)
			return
		}
		writeJSON(w, http.StatusOK, result)
		return
	}
	writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "unknown CircleGroupMembership route"))
}
