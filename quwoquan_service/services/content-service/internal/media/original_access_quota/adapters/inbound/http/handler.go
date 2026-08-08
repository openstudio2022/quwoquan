package http

import (
	"encoding/json"
	"io"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	quotaapp "quwoquan_service/services/content-service/internal/media/original_access_quota/application"
)

type Handler struct{ service *quotaapp.Service }

func NewHandler(service *quotaapp.Service) *Handler {
	if service == nil {
		panic("OriginalAccessQuota HTTP handler requires service")
	}
	return &Handler{service: service}
}

func (handler *Handler) Reserve(writer http.ResponseWriter, request *http.Request) {
	mediaID := strings.TrimSpace(request.PathValue("mediaId"))
	if mediaID == "" {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleContent, "mediaId 不能为空", "missing mediaId"))
		return
	}
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if !ok {
		writeError(writer, request, contentgenerated.AppErrorFromUnauthorized("trusted principal is required"))
		return
	}
	viewerID, ok := principal.Actor.BusinessActorID()
	if !ok {
		writeError(writer, request, contentgenerated.AppErrorFromUnauthorized("business actor is required"))
		return
	}
	var body struct {
		Purpose string `json:"purpose"`
	}
	if request.Body != nil {
		defer request.Body.Close()
		if err := json.NewDecoder(request.Body).Decode(&body); err != nil && err != io.EOF {
			writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
			return
		}
	}
	result, err := handler.service.Reserve(request.Context(), quotaapp.Command{
		AssetID: mediaID, ViewerID: viewerID, Purpose: strings.TrimSpace(body.Purpose),
	})
	if err != nil {
		writeError(writer, request, err)
		return
	}
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(writer).Encode(result)
}

func writeError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
