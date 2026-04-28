package httpadapter

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/entity-service/internal/application"
)

const (
	homepagesPrefix = "/v1/homepages/"
	defaultUserID   = "mock-user"
)

type Handler struct {
	service *application.HomepageService
}

func NewHandler(service *application.HomepageService) *Handler {
	return &Handler{service: service}
}

func (h *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
	})
	mux.HandleFunc("/v1/homepages/search", h.handleSearchHomepages)
	mux.HandleFunc("/v1/homepages/candidates", h.handleCandidates)
	mux.HandleFunc("/v1/homepages/candidates/suggest", h.handleSuggestCandidate)
	mux.HandleFunc(homepagesPrefix, h.handleHomepageRoute)
	return mux
}

func (h *Handler) handleSearchHomepages(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeRuntimeNotFound(w, r)
		return
	}
	query := r.URL.Query()
	items := h.service.SearchHomepages(
		r.Context(),
		query.Get("query"),
		query.Get("homepageType"),
		query.Get("city"),
		query.Get("status"),
		parsePositiveInt(query.Get("limit"), 20),
	)
	writeJSON(w, http.StatusOK, map[string]any{
		"items":      items,
		"nextCursor": nil,
	})
}

func (h *Handler) handleCandidates(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost || r.URL.Path != "/v1/homepages/candidates" {
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

func (h *Handler) handleSuggestCandidate(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeRuntimeNotFound(w, r)
		return
	}
	var input application.HomepageInput
	if err := decodeJSON(r, &input); err != nil {
		writeError(w, r, newBadRequest(err.Error()))
		return
	}
	homepage, err := h.service.SuggestHomepageCandidate(r.Context(), input)
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
		homepage, err := h.service.GetHomepage(r.Context(), homepageID)
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
			// Unreachable for current routes, retained for forward compatibility.
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

func (h *Handler) handleClaimRequests(
	w http.ResponseWriter,
	r *http.Request,
	homepageID string,
	segments []string,
) {
	if len(segments) == 2 && r.Method == http.MethodPost {
		var input application.ClaimRequestInput
		if err := decodeJSON(r, &input); err != nil {
			writeError(w, r, newBadRequest(err.Error()))
			return
		}
		if strings.TrimSpace(input.RequesterUserID) == "" {
			input.RequesterUserID = defaultUserID
		}
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
		var input application.StatusReportInput
		if err := decodeJSON(r, &input); err != nil {
			writeError(w, r, newBadRequest(err.Error()))
			return
		}
		if strings.TrimSpace(input.ReporterUserID) == "" {
			input.ReporterUserID = defaultUserID
		}
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

func newBadRequest(debugMessage string) *application.AppError {
	return &application.AppError{
		StatusCode:   http.StatusBadRequest,
		Code:         "ENTITY.USER.invalid_argument",
		UserMessage:  "请求参数有误，请检查后重试",
		DebugMessage: debugMessage,
	}
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	appErr, ok := err.(*application.AppError)
	if !ok {
		appErr = &application.AppError{
			StatusCode:   http.StatusInternalServerError,
			Code:         "ENTITY.SYSTEM.internal_error",
			UserMessage:  "共享主页暂时不可用，请稍后再试",
			DebugMessage: err.Error(),
		}
	}
	code, parseErr := rterr.ParseCode(appErr.Code)
	if parseErr != nil {
		code = rterr.NewCode(rterr.ModuleEntity, rterr.KindSystem, "internal_error")
	}
	rterr.WriteHTTPError(
		w,
		rterr.NewAppError(
			code,
			appErr.UserMessage,
			appErr.DebugMessage,
		),
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
