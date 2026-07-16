package http

import (
	"fmt"
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	membershipapp "quwoquan_service/services/circle-service/internal/application/circle/circle_membership"
	membershipmodel "quwoquan_service/services/circle-service/internal/domain/circle/circle_membership/model"
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
		expectedVersion, err := parseExpectedVersion(request.Header.Get("If-Match"))
		if err != nil {
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求缺少有效版本", err.Error()))
			return
		}
		result, err := handler.membershipCommands.Leave(request.Context(), membershipapp.LeaveCommand{
			CircleID: circleID, ExpectedVersion: expectedVersion,
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
			Role            string `json:"role"`
			ExpectedVersion int64  `json:"expectedVersion"`
		}
		if err := readStrictJSON(request, &body); err != nil || body.ExpectedVersion <= 0 {
			if err == nil {
				err = fmt.Errorf("expectedVersion must be positive")
			}
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
			return
		}
		result, err := handler.membershipCommands.UpdateRole(request.Context(), membershipapp.UpdateRoleCommand{
			CircleID: circleID, TargetPersonaID: strings.TrimSpace(rest[0]),
			ExpectedVersion: body.ExpectedVersion, Role: membershipmodel.CircleMemberRole(body.Role),
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
	path := strings.TrimPrefix(request.URL.Path, "/v1/personas/")
	parts := strings.Split(strings.Trim(path, "/"), "/")
	if len(parts) != 2 || parts[0] == "" || parts[1] != "circles" {
		writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "expected /v1/personas/{personaId}/circles"))
		return
	}
	result, err := handler.membershipQueries.ListPersonaCircles(
		request.Context(), parts[0], membershipPageLimit(request), request.URL.Query().Get("cursor"),
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
