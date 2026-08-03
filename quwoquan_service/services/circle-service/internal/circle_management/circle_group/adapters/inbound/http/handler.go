package http

import (
	"fmt"
	stdhttp "net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/httpcodec"
	app "quwoquan_service/services/circle-service/internal/circle_management/circle_group/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/ports"
)

type Handler struct {
	commands *app.CommandFacade
	queries  *app.QueryFacade
}

func NewHandler(commands *app.CommandFacade, queries *app.QueryFacade) *Handler {
	if commands == nil || queries == nil {
		panic("CircleGroup Handler requires object command and query facades")
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
	if len(rest) == 1 && rest[0] == "search" {
		handler.serveSearch(writer, request, circleID)
		return
	}
	if len(rest) != 1 || strings.TrimSpace(rest[0]) == "" {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "unknown CircleGroup route"))
		return
	}
	handler.serveResource(writer, request, circleID, strings.TrimSpace(rest[0]))
}

func (handler *Handler) serveCollection(writer stdhttp.ResponseWriter, request *stdhttp.Request, circleID string) {
	switch request.Method {
	case stdhttp.MethodGet:
		result, err := handler.queries.List(request.Context(), ports.ListQuery{
			CircleID: circleID, GroupType: request.URL.Query().Get("groupType"),
			Visibility: request.URL.Query().Get("visibility"), ParentGroupID: request.URL.Query().Get("parentGroupId"),
			NodeType: request.URL.Query().Get("nodeType"), Cursor: request.URL.Query().Get("cursor"),
			Limit: pageLimit(request),
		})
		if err != nil {
			writeError(writer, request, err)
			return
		}
		httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_group")
	case stdhttp.MethodPost:
		var body createBody
		if err := httpcodec.DecodeStrictJSON(request, &body); err != nil || body.StorageEnabled == nil || body.NoticeEnabled == nil {
			if err == nil {
				err = fmt.Errorf("storageEnabled and noticeEnabled are required")
			}
			writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
			return
		}
		result, err := handler.commands.Create(request.Context(), app.CreateCommand{
			CircleID: circleID, ParentGroupID: body.ParentGroupID,
			GroupType: model.CircleGroupType(body.GroupType), NodeType: optionalNodeType(body.NodeType),
			Name: body.Name, Description: body.Description,
			Visibility: model.CircleGroupVisibility(body.Visibility), JoinPolicy: model.CircleGroupJoinPolicy(body.JoinPolicy),
			StorageEnabled: *body.StorageEnabled, NoticeEnabled: *body.NoticeEnabled,
		})
		if err != nil {
			writeError(writer, request, err)
			return
		}
		httpcodec.WriteJSON(writer, stdhttp.StatusCreated, result, "circle_group")
	default:
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "groups accepts GET or POST"))
	}
}

func (handler *Handler) serveSearch(writer stdhttp.ResponseWriter, request *stdhttp.Request, circleID string) {
	if request.Method != stdhttp.MethodGet {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "group search only accepts GET"))
		return
	}
	result, err := handler.queries.Search(request.Context(), ports.SearchRequestFact{
		CircleID: circleID, Query: request.URL.Query().Get("query"),
		Visibility: request.URL.Query().Get("visibility"), GroupType: request.URL.Query().Get("groupType"),
		Cursor: request.URL.Query().Get("cursor"), Limit: pageLimit(request),
	})
	if err != nil {
		writeError(writer, request, err)
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_group")
}

func (handler *Handler) serveResource(writer stdhttp.ResponseWriter, request *stdhttp.Request, circleID, groupID string) {
	switch request.Method {
	case stdhttp.MethodGet:
		result, err := handler.queries.Get(request.Context(), circleID, groupID)
		if err != nil {
			writeError(writer, request, err)
			return
		}
		httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_group")
	case stdhttp.MethodPatch:
		expectedVersion, err := httpcodec.ParsePositiveEntityTag(request.Header.Get("If-Match"))
		if err != nil {
			writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求缺少有效版本", err.Error()))
			return
		}
		var body updateBody
		if err := httpcodec.DecodeStrictJSON(request, &body); err != nil {
			writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
			return
		}
		result, err := handler.commands.Update(request.Context(), app.UpdateCommand{
			CircleID: circleID, GroupID: groupID, ExpectedVersion: expectedVersion,
			ParentGroupID: body.ParentGroupID, NodeType: optionalNodeType(body.NodeType),
			Name: body.Name, Description: body.Description,
			Visibility: optionalVisibility(body.Visibility), JoinPolicy: optionalJoinPolicy(body.JoinPolicy),
			StorageEnabled: body.StorageEnabled, NoticeEnabled: body.NoticeEnabled,
		})
		if err != nil {
			writeError(writer, request, err)
			return
		}
		httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_group")
	case stdhttp.MethodDelete:
		result, err := handler.commands.Archive(request.Context(), app.ArchiveCommand{CircleID: circleID, GroupID: groupID})
		if err != nil {
			writeError(writer, request, err)
			return
		}
		httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_group")
	default:
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "group accepts GET, PATCH or DELETE"))
	}
}

type createBody struct {
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

type updateBody struct {
	ParentGroupID  *string `json:"parentGroupId"`
	NodeType       *string `json:"nodeType"`
	Name           *string `json:"name"`
	Description    *string `json:"description"`
	Visibility     *string `json:"visibility"`
	JoinPolicy     *string `json:"joinPolicy"`
	StorageEnabled *bool   `json:"storageEnabled"`
	NoticeEnabled  *bool   `json:"noticeEnabled"`
}

func optionalNodeType(value *string) *model.OrganizationNodeType {
	if value == nil {
		return nil
	}
	converted := model.OrganizationNodeType(*value)
	return &converted
}

func optionalVisibility(value *string) *model.CircleGroupVisibility {
	if value == nil {
		return nil
	}
	converted := model.CircleGroupVisibility(*value)
	return &converted
}

func optionalJoinPolicy(value *string) *model.CircleGroupJoinPolicy {
	if value == nil {
		return nil
	}
	converted := model.CircleGroupJoinPolicy(*value)
	return &converted
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
