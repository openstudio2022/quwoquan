package http

import (
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	membershipapp "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/application"
	membershipmodel "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/domain/model"
)

func (handler *CircleHandler) handleMemberships(w http.ResponseWriter, request *http.Request, circleID string, rest []string) {
	circleID = strings.TrimSpace(circleID)
	if circleID == "" {
		writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求参数无效", "circleId is required"))
		return
	}
	if len(rest) == 0 {
		switch request.Method {
		case http.MethodPost:
			result, err := handler.membershipCommands.Join(request.Context(), circleID)
			if err != nil {
				writeHTTPError(w, request, err)
				return
			}
			writeJSON(w, http.StatusCreated, result)
		case http.MethodGet:
			limit := membershipPageLimit(request)
			result, err := handler.membershipQueries.ListCircleMemberships(
				request.Context(), circleID, limit, request.URL.Query().Get("cursor"),
			)
			if err != nil {
				writeHTTPError(w, request, err)
				return
			}
			writeJSON(w, http.StatusOK, result)
		default:
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "memberships accepts POST or GET"))
		}
		return
	}
	if len(rest) == 1 && rest[0] == "pending" {
		if request.Method != http.MethodGet {
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "pending memberships only accepts GET"))
			return
		}
		result, err := handler.membershipQueries.ListPendingCircleMemberships(
			request.Context(), circleID, membershipPageLimit(request), request.URL.Query().Get("cursor"),
		)
		if err != nil {
			writeHTTPError(w, request, err)
			return
		}
		writeJSON(w, http.StatusOK, result)
		return
	}
	if len(rest) == 1 && (strings.HasSuffix(rest[0], ":approve") || strings.HasSuffix(rest[0], ":reject")) {
		if request.Method != http.MethodPost {
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "membership approval only accepts POST"))
			return
		}
		target, kind := rest[0], "approve"
		if strings.HasSuffix(target, ":approve") {
			target = strings.TrimSuffix(target, ":approve")
		} else {
			target, kind = strings.TrimSuffix(target, ":reject"), "reject"
		}
		command := membershipapp.DecideCommand{CircleID: circleID, TargetPersonaID: strings.TrimSpace(target)}
		var result membershipapp.CommandResult
		var err error
		if kind == "approve" {
			result, err = handler.membershipCommands.Approve(request.Context(), command)
		} else {
			result, err = handler.membershipCommands.Reject(request.Context(), command)
		}
		if err != nil {
			writeHTTPError(w, request, err)
			return
		}
		writeJSON(w, http.StatusOK, result)
		return
	}
	if len(rest) == 1 && rest[0] == "self" {
		if request.Method == http.MethodGet {
			result, err := handler.membershipQueries.GetMyCircleMembership(request.Context(), circleID)
			if err != nil {
				writeHTTPError(w, request, err)
				return
			}
			writeJSON(w, http.StatusOK, result)
			return
		}
		if request.Method != http.MethodDelete {
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "self membership accepts GET or DELETE"))
			return
		}
		result, err := handler.membershipCommands.Leave(request.Context(), membershipapp.LeaveCommand{
			CircleID: circleID,
		})
		if err != nil {
			writeHTTPError(w, request, err)
			return
		}
		writeJSON(w, http.StatusOK, result)
		return
	}
	if len(rest) == 2 && rest[1] == "role" {
		if request.Method != http.MethodPatch {
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "membership role only accepts PATCH"))
			return
		}
		var body struct {
			Role string `json:"role"`
		}
		if err := readStrictJSON(request, &body); err != nil {
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
			return
		}
		result, err := handler.membershipCommands.UpdateRole(request.Context(), membershipapp.UpdateRoleCommand{
			CircleID: circleID, TargetPersonaID: strings.TrimSpace(rest[0]),
			Role: membershipmodel.CircleMemberRole(body.Role),
		})
		if err != nil {
			writeHTTPError(w, request, err)
			return
		}
		writeJSON(w, http.StatusOK, result)
		return
	}
	writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "unknown CircleMembership command"))
}

func (handler *CircleHandler) handlePersonaCircles(w http.ResponseWriter, request *http.Request) {
	if request.Method != http.MethodGet {
		writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "Persona circles only accepts GET"))
		return
	}
	path := strings.TrimPrefix(request.URL.Path, "/personas/")
	parts := strings.Split(strings.Trim(path, "/"), "/")
	if len(parts) != 2 || parts[0] == "" || parts[1] != "circles" {
		writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "expected /personas/{personaId}/circles"))
		return
	}
	result, err := handler.membershipQueries.ListPersonaCircles(
		request.Context(),
		parts[0],
		request.URL.Query().Get("query"),
		membershipPageLimit(request),
		request.URL.Query().Get("cursor"),
	)
	if err != nil {
		writeHTTPError(w, request, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func membershipPageLimit(request *http.Request) int {
	limit, _ := strconv.Atoi(request.URL.Query().Get("limit"))
	if limit <= 0 {
		return 20
	}
	if limit > 100 {
		return 100
	}
	return limit
}
