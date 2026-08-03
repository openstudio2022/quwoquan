package http

import (
	"fmt"
	stdhttp "net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/httpcodec"
	fileapp "quwoquan_service/services/circle-service/internal/circle_management/circle_file/application"
	filemodel "quwoquan_service/services/circle-service/internal/circle_management/circle_file/domain/model"
	fileports "quwoquan_service/services/circle-service/internal/circle_management/circle_file/domain/ports"
)

type Handler struct {
	commands *fileapp.CommandFacade
	queries  *fileapp.QueryFacade
}

func NewHandler(commands *fileapp.CommandFacade, queries *fileapp.QueryFacade) *Handler {
	if commands == nil || queries == nil {
		panic("CircleFile Handler requires object command and query facades")
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
	if len(rest) != 1 || strings.TrimSpace(rest[0]) == "" {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "unknown CircleFile route"))
		return
	}
	handler.serveResource(writer, request, circleID, strings.TrimSpace(rest[0]))
}

func (handler *Handler) serveCollection(writer stdhttp.ResponseWriter, request *stdhttp.Request, circleID string) {
	switch request.Method {
	case stdhttp.MethodGet:
		result, err := handler.queries.List(request.Context(), fileports.ListQuery{
			CircleID: circleID, GroupID: request.URL.Query().Get("groupId"),
			ParentFolderID: request.URL.Query().Get("parentFolderId"), Cursor: request.URL.Query().Get("cursor"),
			Limit: pageLimit(request),
		})
		if err != nil {
			writeError(writer, request, err)
			return
		}
		httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_file")
	case stdhttp.MethodPost:
		var body struct {
			GroupID        string  `json:"groupId"`
			ParentFolderID *string `json:"parentFolderId"`
			Name           string  `json:"name"`
			FileType       string  `json:"fileType"`
			AssetID        string  `json:"assetId"`
		}
		if err := httpcodec.DecodeStrictJSON(request, &body); err != nil {
			writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
			return
		}
		result, err := handler.commands.Create(request.Context(), fileapp.CreateCommand{
			CircleID: circleID, GroupID: body.GroupID, ParentFolderID: body.ParentFolderID,
			Name: body.Name, FileType: filemodel.CircleFileType(body.FileType), AssetID: body.AssetID,
		})
		if err != nil {
			writeError(writer, request, err)
			return
		}
		httpcodec.WriteJSON(writer, stdhttp.StatusCreated, result, "circle_file")
	default:
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "files accepts GET or POST"))
	}
}

func (handler *Handler) serveResource(writer stdhttp.ResponseWriter, request *stdhttp.Request, circleID, fileID string) {
	switch request.Method {
	case stdhttp.MethodGet:
		result, err := handler.queries.Get(request.Context(), circleID, fileID)
		if err != nil {
			writeError(writer, request, err)
			return
		}
		httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_file")
	case stdhttp.MethodPatch:
		expectedVersion, err := httpcodec.ParsePositiveEntityTag(request.Header.Get("If-Match"))
		if err != nil {
			writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求缺少有效版本", err.Error()))
			return
		}
		var body struct {
			ParentFolderID *string `json:"parentFolderId"`
			Name           *string `json:"name"`
		}
		if err := httpcodec.DecodeStrictJSON(request, &body); err != nil {
			writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
			return
		}
		result, err := handler.commands.Update(request.Context(), fileapp.UpdateCommand{
			CircleID: circleID, FileID: fileID, ExpectedVersion: expectedVersion,
			ParentFolderID: body.ParentFolderID, Name: body.Name,
		})
		if err != nil {
			writeError(writer, request, err)
			return
		}
		httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_file")
	case stdhttp.MethodDelete:
		result, err := handler.commands.Delete(request.Context(), fileapp.DeleteCommand{CircleID: circleID, FileID: fileID})
		if err != nil {
			writeError(writer, request, err)
			return
		}
		httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_file")
	default:
		writeError(writer, request, rterr.NewInvalidArgument(
			rterr.ModuleCircle, "方法不支持", fmt.Sprintf("file route does not accept %s", request.Method),
		))
	}
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
