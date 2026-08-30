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

type Handler struct {
	service    *quotaapp.Service
	auditQuery *quotaapp.AuditQueryFacade
}

type HandlerOption func(*Handler)

// WithAuditQuery wires the owner-scoped audit readback facade
// (GetOriginalImageAccessAudit).
func WithAuditQuery(auditQuery *quotaapp.AuditQueryFacade) HandlerOption {
	return func(handler *Handler) { handler.auditQuery = auditQuery }
}

func NewHandler(service *quotaapp.Service, options ...HandlerOption) *Handler {
	if service == nil {
		panic("OriginalAccessQuota HTTP handler requires service")
	}
	handler := &Handler{service: service}
	for _, option := range options {
		option(handler)
	}
	return handler
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
		ResearchPrincipal: principalHasResearchRole(principal),
	})
	if err != nil {
		writeError(writer, request, err)
		return
	}
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(writer).Encode(result)
}

func (handler *Handler) GetAudit(writer http.ResponseWriter, request *http.Request) {
	if handler.auditQuery == nil {
		writeError(writer, request, contentgenerated.AppErrorFromStorageReadFailed(
			"OriginalAccessQuota audit readback is not configured",
		))
		return
	}
	auditID := strings.TrimSpace(request.PathValue("auditId"))
	if auditID == "" {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleContent, "auditId 不能为空", "missing auditId"))
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
	view, err := handler.auditQuery.GetOriginalImageAccessAudit(
		request.Context(), viewerID, auditID,
	)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(writer).Encode(view)
}

// principalHasResearchRole 从已验签 principal 派生 research 分流标志
// （DEC-032）：role 由服务端签发进 access token，客户端无法自选。
func principalHasResearchRole(principal rtauth.Principal) bool {
	for _, role := range principal.Roles {
		if role == rtauth.RoleResearch {
			return true
		}
	}
	return false
}

func writeError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
