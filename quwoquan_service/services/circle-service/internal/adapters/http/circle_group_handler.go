package http

import (
	"fmt"
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	groupapp "quwoquan_service/services/circle-service/internal/application/circle/circle_group"
	groupmodel "quwoquan_service/services/circle-service/internal/domain/circle/circle_group/model"
	groupports "quwoquan_service/services/circle-service/internal/domain/circle/circle_group/ports"
)

func (handler *CircleHandler) handleGroups(w http.ResponseWriter, request *http.Request, circleID string, rest []string) {
	circleID = strings.TrimSpace(circleID)
	if circleID == "" {
		writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求参数无效", "circleId is required"))
		return
	}
	if len(rest) == 0 {
		switch request.Method {
		case http.MethodGet:
			result, err := handler.groupQueries.List(request.Context(), groupports.ListQuery{
				CircleID: circleID, GroupType: request.URL.Query().Get("groupType"),
				Visibility: request.URL.Query().Get("visibility"), ParentGroupID: request.URL.Query().Get("parentGroupId"),
				NodeType: request.URL.Query().Get("nodeType"), Cursor: request.URL.Query().Get("cursor"),
				Limit: groupPageLimit(request),
			})
			if err != nil {
				writeHTTPError(w, request, err)
				return
			}
			writeJSON(w, http.StatusOK, result)
		case http.MethodPost:
			var body createCircleGroupBody
			if err := readStrictJSON(request, &body); err != nil || body.StorageEnabled == nil || body.NoticeEnabled == nil {
				if err == nil {
					err = fmt.Errorf("storageEnabled and noticeEnabled are required")
				}
				writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
				return
			}
			result, err := handler.groupCommands.Create(request.Context(), groupapp.CreateCommand{
				CircleID: circleID, ParentGroupID: body.ParentGroupID,
				GroupType: groupmodel.CircleGroupType(body.GroupType), NodeType: optionalNodeType(body.NodeType),
				Name: body.Name, Description: body.Description,
				Visibility:     groupmodel.CircleGroupVisibility(body.Visibility),
				JoinPolicy:     groupmodel.CircleGroupJoinPolicy(body.JoinPolicy),
				StorageEnabled: *body.StorageEnabled, NoticeEnabled: *body.NoticeEnabled,
			})
			if err != nil {
				writeHTTPError(w, request, err)
				return
			}
			writeJSON(w, http.StatusCreated, result)
		default:
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "groups accepts GET or POST"))
		}
		return
	}
	if len(rest) == 1 && rest[0] == "search" {
		if request.Method != http.MethodGet {
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "group search only accepts GET"))
			return
		}
		result, err := handler.groupQueries.Search(request.Context(), groupports.SearchQuery{
			CircleID: circleID, Query: request.URL.Query().Get("query"),
			Visibility: request.URL.Query().Get("visibility"), GroupType: request.URL.Query().Get("groupType"),
			Cursor: request.URL.Query().Get("cursor"), Limit: groupPageLimit(request),
		})
		if err != nil {
			writeHTTPError(w, request, err)
			return
		}
		writeJSON(w, http.StatusOK, result)
		return
	}
	if len(rest) >= 2 && strings.TrimSpace(rest[0]) != "" && rest[1] == "memberships" {
		handler.handleGroupMemberships(w, request, circleID, strings.TrimSpace(rest[0]), rest[2:])
		return
	}
	if len(rest) != 1 || strings.TrimSpace(rest[0]) == "" {
		writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "unknown CircleGroup route"))
		return
	}
	groupID := strings.TrimSpace(rest[0])
	switch request.Method {
	case http.MethodGet:
		result, err := handler.groupQueries.Get(request.Context(), circleID, groupID)
		if err != nil {
			writeHTTPError(w, request, err)
			return
		}
		writeJSON(w, http.StatusOK, result)
	case http.MethodPatch:
		expectedVersion, err := parseExpectedVersion(request.Header.Get("If-Match"))
		if err != nil {
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求缺少有效版本", err.Error()))
			return
		}
		var body updateCircleGroupBody
		if err := readStrictJSON(request, &body); err != nil {
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
			return
		}
		result, err := handler.groupCommands.Update(request.Context(), groupapp.UpdateCommand{
			CircleID: circleID, GroupID: groupID, ExpectedVersion: expectedVersion,
			ParentGroupID: body.ParentGroupID, NodeType: optionalNodeType(body.NodeType),
			Name: body.Name, Description: body.Description,
			Visibility: optionalVisibility(body.Visibility), JoinPolicy: optionalJoinPolicy(body.JoinPolicy),
			StorageEnabled: body.StorageEnabled, NoticeEnabled: body.NoticeEnabled,
		})
		if err != nil {
			writeHTTPError(w, request, err)
			return
		}
		writeJSON(w, http.StatusOK, result)
	case http.MethodDelete:
		result, err := handler.groupCommands.Archive(request.Context(), groupapp.ArchiveCommand{
			CircleID: circleID, GroupID: groupID,
		})
		if err != nil {
			writeHTTPError(w, request, err)
			return
		}
		writeJSON(w, http.StatusOK, result)
	default:
		writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "group accepts GET, PATCH or DELETE"))
	}
}

type createCircleGroupBody struct {
	ParentGroupID  *string `json:"parentGroupId"`
	GroupType      string  `json:"groupType"`
	NodeType       *string `json:"nodeType"`
	Name           string  `json:"name"`
	Description    string  `json:"description"`
	Visibility     string  `json:"visibility"`
	JoinPolicy     string  `json:"joinPolicy"`
	StorageEnabled *bool   `json:"storageEnabled"`
	NoticeEnabled  *bool   `json:"noticeEnabled"`
}

type updateCircleGroupBody struct {
	ParentGroupID  *string `json:"parentGroupId"`
	NodeType       *string `json:"nodeType"`
	Name           *string `json:"name"`
	Description    *string `json:"description"`
	Visibility     *string `json:"visibility"`
	JoinPolicy     *string `json:"joinPolicy"`
	StorageEnabled *bool   `json:"storageEnabled"`
	NoticeEnabled  *bool   `json:"noticeEnabled"`
}

func optionalNodeType(value *string) *groupmodel.OrganizationNodeType {
	if value == nil {
		return nil
	}
	converted := groupmodel.OrganizationNodeType(*value)
	return &converted
}

func optionalVisibility(value *string) *groupmodel.CircleGroupVisibility {
	if value == nil {
		return nil
	}
	converted := groupmodel.CircleGroupVisibility(*value)
	return &converted
}

func optionalJoinPolicy(value *string) *groupmodel.CircleGroupJoinPolicy {
	if value == nil {
		return nil
	}
	converted := groupmodel.CircleGroupJoinPolicy(*value)
	return &converted
}

func groupPageLimit(request *http.Request) int {
	limit, _ := strconv.Atoi(request.URL.Query().Get("limit"))
	if limit <= 0 {
		return 20
	}
	if limit > 100 {
		return 100
	}
	return limit
}
