package httpadapter

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	entitygenerated "quwoquan_service/services/entity-service/generated/entity_homepage/homepage"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
	reviewapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/application"
)

const homepagesPrefix = "/homepages/"

type Handler struct {
	service *application.HomepageService
	reviews *reviewapp.Facade
}

func NewHandler(service *application.HomepageService) *Handler {
	return &Handler{service: service}
}

// WithReviewFacade 装配 HomepageReview 对象 facade（composition root 调用）。
func (h *Handler) WithReviewFacade(facade *reviewapp.Facade) *Handler {
	h.reviews = facade
	return h
}

func (h *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
	})
	mux.HandleFunc("/homepages/search", h.handleSearchHomepages)
	mux.HandleFunc("/homepages/candidates", h.handleCandidates)
	mux.HandleFunc("/homepages/candidates/suggest", h.handleSuggestCandidate)
	mux.HandleFunc("/homepage-claim-requests", h.handleClaimRequestQueue)
	mux.HandleFunc("/homepage-status-reports", h.handleStatusReportQueue)
	mux.HandleFunc("/homepage-reviews/", h.handleReviewByID)
	mux.HandleFunc(homepagesPrefix, h.handleHomepageRoute)
	return mux
}

func (h *Handler) handleSearchHomepages(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeRuntimeNotFound(w, r)
		return
	}
	query := r.URL.Query()
	result, err := h.service.SearchHomepages(
		r.Context(),
		query.Get("query"),
		query.Get("homepageType"),
		query.Get("city"),
		query.Get("status"),
		query.Get("cursor"),
		parsePositiveInt(query.Get("limit"), 20),
	)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items":      result.Items,
		"nextCursor": result.NextCursor,
	})
}

func (h *Handler) handleCandidates(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/homepages/candidates" {
		writeRuntimeNotFound(w, r)
		return
	}
	if r.Method == http.MethodGet {
		query := r.URL.Query()
		result, err := h.service.SearchHomepages(
			r.Context(),
			query.Get("query"),
			query.Get("homepageType"),
			query.Get("city"),
			"candidate",
			query.Get("cursor"),
			parsePositiveInt(query.Get("limit"), 20),
		)
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, result)
		return
	}
	if r.Method != http.MethodPost {
		writeRuntimeNotFound(w, r)
		return
	}
	var input application.HomepageInput
	if err := decodeJSON(r, &input); err != nil {
		writeError(w, r, newBadRequest(err.Error()))
		return
	}
	homepage, err := h.service.IntakeHomepageCandidate(r.Context(), input, "owner_created")
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, homepage)
}

func (h *Handler) handleClaimRequestQueue(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeRuntimeNotFound(w, r)
		return
	}
	query := r.URL.Query()
	status := query.Get("status")
	if strings.TrimSpace(status) == "" {
		status = "pending_review"
	}
	result, err := h.service.ListHomepageClaimRequests(
		r.Context(),
		query.Get("homepageId"),
		status,
		query.Get("cursor"),
		parsePositiveInt(query.Get("limit"), 20),
	)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) handleStatusReportQueue(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeRuntimeNotFound(w, r)
		return
	}
	query := r.URL.Query()
	status := query.Get("status")
	if strings.TrimSpace(status) == "" {
		status = "pending_review"
	}
	result, err := h.service.ListHomepageStatusReports(
		r.Context(),
		query.Get("homepageId"),
		status,
		query.Get("cursor"),
		parsePositiveInt(query.Get("limit"), 20),
	)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) handleSuggestCandidate(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeRuntimeNotFound(w, r)
		return
	}
	var request struct {
		application.HomepageInput
		SourcePlaceID string `json:"sourcePlaceId"`
	}
	if err := decodeJSON(r, &request); err != nil {
		writeError(w, r, newBadRequest(err.Error()))
		return
	}
	if sourcePlaceID := strings.TrimSpace(request.SourcePlaceID); sourcePlaceID != "" {
		request.HomepageInput.LookupAliases = []string{sourcePlaceID}
	}
	homepage, err := h.service.SuggestHomepageCandidate(r.Context(), request.HomepageInput)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, homepage)
}

func (h *Handler) handleHomepageRoute(w http.ResponseWriter, r *http.Request) {
	remainder := strings.TrimPrefix(r.URL.Path, homepagesPrefix)
	if remainder == r.URL.Path {
		writeRuntimeNotFound(w, r)
		return
	}
	segments := strings.Split(strings.Trim(remainder, "/"), "/")
	if len(segments) == 0 || segments[0] == "" {
		writeRuntimeNotFound(w, r)
		return
	}
	if segments[0] == "candidates" && len(segments) == 2 && r.Method == http.MethodPost && strings.HasSuffix(segments[1], ":publish") {
		homepageID := strings.TrimSuffix(segments[1], ":publish")
		homepage, err := h.service.PublishHomepageCandidate(r.Context(), homepageID)
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, homepage)
		return
	}
	homepageID := segments[0]
	if len(segments) == 1 {
		if r.Method != http.MethodGet {
			writeRuntimeNotFound(w, r)
			return
		}
		homepage, err := h.service.GetHomepageForViewer(
			r.Context(),
			homepageID,
			resolveViewerID(r),
		)
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, homepage)
		return
	}

	switch segments[1] {
	case "shell":
		if r.Method != http.MethodGet || len(segments) != 2 {
			writeRuntimeNotFound(w, r)
			return
		}
		shell, err := h.service.GetHomepageShell(r.Context(), homepageID)
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, shell)
	case "introduction":
		if r.Method != http.MethodGet || len(segments) != 2 {
			writeRuntimeNotFound(w, r)
			return
		}
		introduction, err := h.service.GetHomepageIntroduction(r.Context(), homepageID)
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, introduction)
	case "review-summary":
		if r.Method != http.MethodGet || len(segments) != 2 {
			writeRuntimeNotFound(w, r)
			return
		}
		summary, err := h.service.GetHomepageReviewSummary(r.Context(), homepageID)
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, summary)
	case "related-groups":
		if r.Method != http.MethodGet || len(segments) != 2 {
			writeRuntimeNotFound(w, r)
			return
		}
		summary, err := h.service.GetHomepageRelatedGroups(r.Context(), homepageID)
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, summary)
	case "impact":
		if r.Method != http.MethodGet || len(segments) != 2 {
			writeRuntimeNotFound(w, r)
			return
		}
		summary, err := h.service.GetHomepageImpact(r.Context(), homepageID)
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, summary)
	case "object-page-bundle":
		if r.Method != http.MethodGet || len(segments) != 2 {
			writeRuntimeNotFound(w, r)
			return
		}
		query := r.URL.Query()
		bundle, err := h.service.GetObjectPageBundle(
			r.Context(),
			resolveViewerID(r),
			homepageID,
			query.Get("referralSource"),
			query.Get("feedRequestId"),
			query.Get("recommendationTraceId"),
			query.Get("experimentBucket"),
			query.Get("rolloutCohort"),
		)
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, bundle)
	case "reviews":
		h.handleHomepageReviews(w, r, homepageID, segments)
	case "claim-requests":
		h.handleClaimRequests(w, r, homepageID, segments)
	case "claimed-basics":
		if r.Method != http.MethodPatch || len(segments) != 2 {
			writeRuntimeNotFound(w, r)
			return
		}
		var input application.HomepageBasicInput
		if err := decodeJSON(r, &input); err != nil {
			writeError(w, r, newBadRequest(err.Error()))
			return
		}
		homepage, err := h.service.UpdateClaimedHomepageBasics(r.Context(), homepageID, input)
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, homepage)
	case "status-reports":
		h.handleStatusReports(w, r, homepageID, segments)
	default:
		if strings.HasSuffix(segments[0], ":publish") && r.Method == http.MethodPost {
			writeRuntimeNotFound(w, r)
			return
		}
		if len(segments) == 1 && strings.HasSuffix(homepageID, ":publish") {
			writeRuntimeNotFound(w, r)
			return
		}
		if len(segments) == 1 && strings.HasSuffix(segments[0], ":publish") {
			writeRuntimeNotFound(w, r)
			return
		}
		if len(segments) == 0 {
			writeRuntimeNotFound(w, r)
			return
		}
		writeRuntimeNotFound(w, r)
	}
}

// resolveViewerID 从可信 operation.Context 取 viewer persona（匿名读允许为空）；
// 禁止读取客户端可伪造的 identity header。
func resolveViewerID(r *http.Request) string {
	if r == nil {
		return ""
	}
	invocation, ok := operation.FromContext(r.Context())
	if !ok {
		return ""
	}
	return strings.TrimSpace(invocation.Actor.PersonaID)
}

func (h *Handler) handleClaimRequests(
	w http.ResponseWriter,
	r *http.Request,
	homepageID string,
	segments []string,
) {
	if len(segments) == 2 && r.Method == http.MethodPost {
		actorID, err := requiredPersonaActor(r)
		if err != nil {
			writeError(w, r, err)
			return
		}
		var input application.ClaimRequestInput
		if err := decodeJSON(r, &input); err != nil {
			writeError(w, r, newBadRequest(err.Error()))
			return
		}
		// requester 身份只来自可信 operation.Context，不接收 body 身份。
		input.RequesterPersonaID = actorID
		request, err := h.service.CreateHomepageClaimRequest(r.Context(), homepageID, input)
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, http.StatusCreated, request)
		return
	}
	if len(segments) == 3 && r.Method == http.MethodPost && strings.HasSuffix(segments[2], ":review") {
		var input application.ClaimReviewInput
		if err := decodeJSON(r, &input); err != nil {
			writeError(w, r, newBadRequest(err.Error()))
			return
		}
		claimRequestID := strings.TrimSuffix(segments[2], ":review")
		request, err := h.service.ReviewHomepageClaimRequest(r.Context(), homepageID, claimRequestID, input)
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, request)
		return
	}
	writeRuntimeNotFound(w, r)
}

func (h *Handler) handleStatusReports(
	w http.ResponseWriter,
	r *http.Request,
	homepageID string,
	segments []string,
) {
	if len(segments) == 2 && r.Method == http.MethodPost {
		actorID, err := requiredPersonaActor(r)
		if err != nil {
			writeError(w, r, err)
			return
		}
		var input application.StatusReportInput
		if err := decodeJSON(r, &input); err != nil {
			writeError(w, r, newBadRequest(err.Error()))
			return
		}
		// reporter 身份只来自可信 operation.Context，不接收 body 身份。
		input.ReporterPersonaID = actorID
		report, err := h.service.CreateHomepageStatusReport(r.Context(), homepageID, input)
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, http.StatusCreated, report)
		return
	}
	if len(segments) == 3 && r.Method == http.MethodPost && strings.HasSuffix(segments[2], ":review") {
		var input application.StatusReportReviewInput
		if err := decodeJSON(r, &input); err != nil {
			writeError(w, r, newBadRequest(err.Error()))
			return
		}
		reportID := strings.TrimSuffix(segments[2], ":review")
		report, err := h.service.ReviewHomepageStatusReport(r.Context(), homepageID, reportID, input)
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, report)
		return
	}
	writeRuntimeNotFound(w, r)
}

func decodeJSON(r *http.Request, target any) error {
	defer r.Body.Close()
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	return decoder.Decode(target)
}

func parsePositiveInt(raw string, fallback int) int {
	value, err := strconv.Atoi(strings.TrimSpace(raw))
	if err != nil || value <= 0 {
		return fallback
	}
	return value
}

func newBadRequest(debugMessage string) *rterr.AppError {
	return entitygenerated.AppErrorFromInvalidArgument(debugMessage)
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	var appErr *rterr.AppError
	if !errors.As(err, &appErr) {
		appErr = entitygenerated.AppErrorFromInternalError(err.Error())
	}
	rterr.WriteHTTPError(
		w,
		appErr,
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}

func writeRuntimeNotFound(w http.ResponseWriter, r *http.Request) {
	rterr.WriteHTTPError(
		w,
		rterr.NewAppError(
			rterr.NewCode(rterr.ModuleEntity, rterr.KindUser, "not_found"),
			"接口不存在",
			"route not found",
		),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}
