package http

import (
	"fmt"
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	fileapp "quwoquan_service/services/circle-service/internal/circle_management/circle_file/application"
	filemodel "quwoquan_service/services/circle-service/internal/circle_management/circle_file/domain/model"
	fileports "quwoquan_service/services/circle-service/internal/circle_management/circle_file/domain/ports"
)

func (handler *CircleHandler) handleFiles(w http.ResponseWriter, request *http.Request, circleID string, rest []string) {
	circleID = strings.TrimSpace(circleID)
	if circleID == "" {
		writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求参数无效", "circleId is required"))
		return
	}
	if len(rest) == 0 {
		switch request.Method {
		case http.MethodGet:
			result, err := handler.fileQueries.List(request.Context(), fileports.ListQuery{
				CircleID: circleID, GroupID: request.URL.Query().Get("groupId"),
				ParentFolderID: request.URL.Query().Get("parentFolderId"), Cursor: request.URL.Query().Get("cursor"),
				Limit: filePageLimit(request),
			})
			if err != nil {
				writeHTTPError(w, request, err)
				return
			}
			writeJSON(w, http.StatusOK, result)
		case http.MethodPost:
			var body struct {
				GroupID        string  `json:"groupId"`
				ParentFolderID *string `json:"parentFolderId"`
				Name           string  `json:"name"`
				FileType       string  `json:"fileType"`
				AssetID        string  `json:"assetId"`
			}
			if err := readStrictJSON(request, &body); err != nil {
				writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
				return
			}
			result, err := handler.fileCommands.Create(request.Context(), fileapp.CreateCommand{
				CircleID: circleID, GroupID: body.GroupID, ParentFolderID: body.ParentFolderID,
				Name: body.Name, FileType: filemodel.CircleFileType(body.FileType), AssetID: body.AssetID,
			})
			if err != nil {
				writeHTTPError(w, request, err)
				return
			}
			writeJSON(w, http.StatusCreated, result)
		default:
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "files accepts GET or POST"))
		}
		return
	}
	if len(rest) != 1 || strings.TrimSpace(rest[0]) == "" {
		writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "unknown CircleFile route"))
		return
	}
	fileID := strings.TrimSpace(rest[0])
	switch request.Method {
	case http.MethodGet:
		result, err := handler.fileQueries.Get(request.Context(), circleID, fileID)
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
		var body struct {
			ParentFolderID *string `json:"parentFolderId"`
			Name           *string `json:"name"`
		}
		if err := readStrictJSON(request, &body); err != nil {
			writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
			return
		}
		result, err := handler.fileCommands.Update(request.Context(), fileapp.UpdateCommand{
			CircleID: circleID, FileID: fileID, ExpectedVersion: expectedVersion,
			ParentFolderID: body.ParentFolderID, Name: body.Name,
		})
		if err != nil {
			writeHTTPError(w, request, err)
			return
		}
		writeJSON(w, http.StatusOK, result)
	case http.MethodDelete:
		result, err := handler.fileCommands.Delete(request.Context(), fileapp.DeleteCommand{
			CircleID: circleID, FileID: fileID,
		})
		if err != nil {
			writeHTTPError(w, request, err)
			return
		}
		writeJSON(w, http.StatusOK, result)
	default:
		writeHTTPError(w, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", fmt.Sprintf("file route does not accept %s", request.Method)))
	}
}

func filePageLimit(request *http.Request) int {
	limit, _ := strconv.Atoi(request.URL.Query().Get("limit"))
	if limit <= 0 {
		return 20
	}
	if limit > 100 {
		return 100
	}
	return limit
}
