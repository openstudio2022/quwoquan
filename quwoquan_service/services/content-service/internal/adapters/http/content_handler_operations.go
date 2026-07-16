package http

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	reportapp "quwoquan_service/services/content-service/internal/application/report"
	reportmodel "quwoquan_service/services/content-service/internal/domain/report/model"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

func (h *ContentHandler) handleNotImplemented(w http.ResponseWriter, r *http.Request, operation string) {
	switch operation {
	case "LikePost":
		h.handleLikePost(w, r, postIDFromPath(r.URL.Path))
		return
	case "UnlikePost":
		h.handleUnlikePost(w, r, postIDFromPath(r.URL.Path))
		return
	case "GetContentReactionState":
		h.handleGetReactionState(w, r, postIDFromPath(r.URL.Path))
		return
	case "GetMyFootprint":
		h.handleGetMyFootprint(w, r)
		return
	case "CreateComment":
		h.handleCreateComment(w, r, postIDFromPath(r.URL.Path))
		return
	case "PublishPost":
		h.handlePublishPost(w, r)
		return
	case "UpdatePostSettings":
		h.handleUpdatePostSettings(w, r)
		return
	case "PromotePostToWork":
		h.handlePromotePostToWork(w, r)
		return
	case "DeletePost":
		h.handleDeletePost(w, r)
		return
	case "GenerateArticleSummary":
		h.handleGenerateArticleSummary(w, r)
		return
	case "ListComments":
		h.handleListComments(w, r, postIDFromPath(r.URL.Path))
		return
	case "ListCommentReplies":
		h.handleListCommentReplies(w, r)
		return
	case "ReactToComment":
		h.handleReactToComment(w, r, commentIDFromPath(r.URL.Path))
		return
	case "BindMediaAssetsToComment":
		h.handleBindMediaAssetsToComment(w, r, commentIDFromPath(r.URL.Path))
		return
	case "DeleteComment":
		h.handleDeleteComment(w, r)
		return
	case "PinComment":
		h.handleSetCommentPinned(w, r, true)
		return
	case "UnpinComment":
		h.handleSetCommentPinned(w, r, false)
		return
	case "GetCounters":
		h.handleGetCounters(w, r, postIDFromPath(r.URL.Path))
		return
	case "GetHelperRead":
		h.handleGetHelperRead(w, r)
		return
	case "ListUserPosts":
		h.handleListUserPosts(w, r)
		return
	case "ListCommentsByAuthor":
		h.handleListCommentsByAuthor(w, r)
		return
	case "ListCommentsForPostAuthor":
		h.handleListCommentsForPostAuthor(w, r)
		return
	case "GetAppConfig":
		h.handleGetAppConfig(w, r)
		return
	}
	writeHTTPError(w, r, rterr.NewAppError(
		rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "unavailable"),
		"接口暂未开放",
		"operation not implemented: "+operation+" "+r.Method+" "+r.URL.Path,
	))
}

func (h *ContentHandler) handleListReports(w http.ResponseWriter, r *http.Request) {
	if h.reportService == nil {
		h.writeReportServiceUnavailable(w, r)
		return
	}
	if _, ok := verifiedReportOperatorAccountID(w, r); !ok {
		return
	}
	limit := 20
	if rawLimit := strings.TrimSpace(r.URL.Query().Get("limit")); rawLimit != "" {
		parsed, err := strconv.Atoi(rawLimit)
		if err != nil || parsed < 1 || parsed > 100 {
			writeHTTPError(
				w,
				r,
				contentgenerated.AppErrorFromInvalidArgument(
					"ListReports limit must be an integer between 1 and 100",
				),
			)
			return
		}
		limit = parsed
	}
	payload, err := h.reportService.ListReports(
		r.Context(),
		reportapp.ListReportsQuery{Limit: limit},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, payload)
}

func (h *ContentHandler) handleGetReport(w http.ResponseWriter, r *http.Request) {
	if h.reportService == nil {
		h.writeReportServiceUnavailable(w, r)
		return
	}
	if _, ok := verifiedReportOperatorAccountID(w, r); !ok {
		return
	}
	reportID := pathParamAfter(r.URL.Path, "/v1/content/reports/", "")
	if reportID == "" {
		writeHTTPError(
			w,
			r,
			contentgenerated.AppErrorFromInvalidArgument("GetReport requires reportId"),
		)
		return
	}
	payload, err := h.reportService.GetReport(
		r.Context(),
		reportapp.GetReportQuery{ReportID: reportID},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, payload)
}

func (h *ContentHandler) handleBeginReportReview(w http.ResponseWriter, r *http.Request) {
	if h.reportService == nil {
		h.writeReportServiceUnavailable(w, r)
		return
	}
	operatorAccountID, ok := verifiedReportOperatorAccountID(w, r)
	if !ok {
		return
	}
	if err := decodeEmptyReportReviewRequest(r); err != nil {
		writeHTTPError(
			w,
			r,
			contentgenerated.AppErrorFromInvalidArgument(
				"BeginReportReview request body must be empty",
			),
		)
		return
	}
	reportID := pathParamAfter(r.URL.Path, "/v1/content/reports/", "/review")
	if reportID == "" {
		writeHTTPError(
			w,
			r,
			contentgenerated.AppErrorFromInvalidArgument(
				"BeginReportReview requires reportId",
			),
		)
		return
	}
	payload, err := h.reportService.BeginReview(
		r.Context(),
		reportapp.BeginReviewReportCommand{
			ReportID:   reportID,
			ReviewerID: operatorAccountID,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, payload)
}

func (h *ContentHandler) handleResolveReport(w http.ResponseWriter, r *http.Request) {
	if h.reportService == nil {
		h.writeReportServiceUnavailable(w, r)
		return
	}
	operatorAccountID, ok := verifiedReportOperatorAccountID(w, r)
	if !ok {
		return
	}
	var request struct {
		Resolution reportmodel.Resolution `json:"resolution"`
	}
	if err := decodeStrictReportJSON(r, &request); err != nil {
		writeHTTPError(
			w,
			r,
			contentgenerated.AppErrorFromInvalidArgument(
				"ResolveReport request body is invalid: "+err.Error(),
			),
		)
		return
	}
	reportID := pathParamAfter(r.URL.Path, "/v1/content/reports/", "")
	if reportID == "" {
		writeHTTPError(
			w,
			r,
			contentgenerated.AppErrorFromInvalidArgument("ResolveReport requires reportId"),
		)
		return
	}
	payload, err := h.reportService.Resolve(
		r.Context(),
		reportapp.ResolveReportCommand{
			ReportID:   reportID,
			ReviewerID: operatorAccountID,
			Resolution: request.Resolution,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, payload)
}

func verifiedReportOperatorAccountID(w http.ResponseWriter, r *http.Request) (string, bool) {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	accountID := strings.TrimSpace(principal.Actor.AccountID)
	descriptor, descriptorOK := rtauth.OperationDescriptorFromContext(r.Context())
	if ok &&
		accountID != "" &&
		descriptorOK &&
		descriptor.Principal == "operator" &&
		descriptor.CommercialStatus == "ready" {
		return accountID, true
	}
	writeHTTPError(
		w,
		r,
		contentgenerated.AppErrorFromUnauthorized(
			"verified ready operator operation principal is required for report operations",
		),
	)
	return "", false
}

func (h *ContentHandler) writeReportServiceUnavailable(w http.ResponseWriter, r *http.Request) {
	writeHTTPError(
		w,
		r,
		contentgenerated.AppErrorFromStorageReadFailed(
			"report service facades are not configured",
		),
	)
}

func decodeEmptyReportReviewRequest(r *http.Request) error {
	if r.Body == nil {
		return nil
	}
	var payload struct{}
	err := decodeStrictReportJSON(r, &payload)
	if err == io.EOF {
		return nil
	}
	return err
}

func decodeStrictReportJSON(r *http.Request, target any) error {
	if r.Body == nil {
		return io.EOF
	}
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return rterr.NewInvalidArgument(
				rterr.ModuleContent,
				"请求体包含多个 JSON 值",
				"report request contains multiple JSON values",
			)
		}
		return err
	}
	return nil
}
