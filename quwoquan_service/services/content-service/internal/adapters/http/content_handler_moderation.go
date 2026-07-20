package http

import (
	"net/http"
	"strconv"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	moderationapp "quwoquan_service/services/content-service/internal/application/moderation"
	moderationmodel "quwoquan_service/services/content-service/internal/domain/moderation/model"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

// PostModerationCase 的 internal transport 装配。auth/scope/token 由 route
// guard（generated operation descriptor）先行执行；operator 命令在此再做
// principal 二次校验（与 report 队列同源的双保险，客户端 guard 不是安全边界）。

func (h *ContentHandler) handleOpenPostModerationCase(w http.ResponseWriter, r *http.Request) {
	if h.moderationService == nil {
		h.writeModerationServiceUnavailable(w, r)
		return
	}
	postID := strings.TrimSpace(r.PathValue("postId"))
	var body struct {
		PostVersion   int64  `json:"postVersion"`
		ContentDigest string `json:"contentDigest"`
	}
	if err := decodeStrictReportJSON(r, &body); err != nil {
		writeHTTPError(
			w,
			r,
			contentgenerated.AppErrorFromInvalidArgument(
				"OpenPostModerationCase request body is invalid: "+err.Error(),
			),
		)
		return
	}
	result, err := h.moderationService.OpenPostModerationCase(
		r.Context(),
		moderationapp.OpenPostModerationCaseCommand{
			PostID:        postID,
			PostVersion:   body.PostVersion,
			ContentDigest: body.ContentDigest,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *ContentHandler) handleReviewPostModerationCase(w http.ResponseWriter, r *http.Request) {
	if h.moderationService == nil {
		h.writeModerationServiceUnavailable(w, r)
		return
	}
	reviewerID, ok := verifiedModerationOperatorAccountID(w, r)
	if !ok {
		return
	}
	var body struct {
		CaseID string `json:"caseId"`
	}
	if err := decodeStrictReportJSON(r, &body); err != nil {
		writeHTTPError(
			w,
			r,
			contentgenerated.AppErrorFromInvalidArgument(
				"ReviewPostModerationCase request body is invalid: "+err.Error(),
			),
		)
		return
	}
	result, err := h.moderationService.ReviewPostModerationCase(
		r.Context(),
		moderationapp.ReviewPostModerationCaseCommand{
			CaseID:     body.CaseID,
			ReviewerID: reviewerID,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *ContentHandler) handleDecidePostModeration(w http.ResponseWriter, r *http.Request) {
	if h.moderationService == nil {
		h.writeModerationServiceUnavailable(w, r)
		return
	}
	reviewerID, ok := verifiedModerationOperatorAccountID(w, r)
	if !ok {
		return
	}
	var body struct {
		CaseID         string `json:"caseId"`
		Decision       string `json:"decision"`
		DecisionReason string `json:"decisionReason"`
	}
	if err := decodeStrictReportJSON(r, &body); err != nil {
		writeHTTPError(
			w,
			r,
			contentgenerated.AppErrorFromInvalidArgument(
				"DecidePostModeration request body is invalid: "+err.Error(),
			),
		)
		return
	}
	result, err := h.moderationService.DecidePostModerationCase(
		r.Context(),
		moderationapp.DecidePostModerationCaseCommand{
			CaseID:         body.CaseID,
			ReviewerID:     reviewerID,
			Decision:       moderationmodel.Decision(strings.TrimSpace(body.Decision)),
			DecisionReason: body.DecisionReason,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *ContentHandler) handleSupersedePostModerationCase(w http.ResponseWriter, r *http.Request) {
	if h.moderationService == nil {
		h.writeModerationServiceUnavailable(w, r)
		return
	}
	var body struct {
		CaseID string `json:"caseId"`
	}
	if err := decodeStrictReportJSON(r, &body); err != nil {
		writeHTTPError(
			w,
			r,
			contentgenerated.AppErrorFromInvalidArgument(
				"SupersedePostModerationCase request body is invalid: "+err.Error(),
			),
		)
		return
	}
	result, err := h.moderationService.SupersedePostModerationCase(
		r.Context(),
		moderationapp.SupersedePostModerationCaseCommand{CaseID: body.CaseID},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *ContentHandler) handleGetCurrentPostModerationCase(
	w http.ResponseWriter,
	r *http.Request,
) {
	if h.moderationService == nil {
		h.writeModerationServiceUnavailable(w, r)
		return
	}
	if _, ok := verifiedModerationOperatorAccountID(w, r); !ok {
		return
	}
	postID := strings.TrimSpace(r.PathValue("postId"))
	result, err := h.moderationService.GetCurrentPostModerationCase(
		r.Context(),
		moderationapp.GetCurrentPostModerationCaseQuery{PostID: postID},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *ContentHandler) handleGetPostPublicationEligibility(w http.ResponseWriter, r *http.Request) {
	if h.moderationService == nil {
		h.writeModerationServiceUnavailable(w, r)
		return
	}
	postID := strings.TrimSpace(r.PathValue("postId"))
	query := r.URL.Query()
	postVersion, err := parseInt64QueryParam(query.Get("postVersion"))
	if err != nil {
		writeHTTPError(
			w,
			r,
			contentgenerated.AppErrorFromInvalidArgument(
				"GetPostPublicationEligibility postVersion must be a positive integer",
			),
		)
		return
	}
	slice, err := h.moderationService.GetPostPublicationEligibility(
		r.Context(),
		moderationapp.GetPostPublicationEligibilityQuery{
			PostID:        postID,
			PostVersion:   postVersion,
			ContentDigest: strings.TrimSpace(query.Get("contentDigest")),
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, slice)
}

func parseInt64QueryParam(raw string) (int64, error) {
	value, err := strconv.ParseInt(strings.TrimSpace(raw), 10, 64)
	if err != nil || value < 1 {
		return 0, strconv.ErrSyntax
	}
	return value, nil
}

func verifiedModerationOperatorAccountID(
	w http.ResponseWriter,
	r *http.Request,
) (string, bool) {
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
			"verified ready operator operation principal is required for moderation commands",
		),
	)
	return "", false
}

func (h *ContentHandler) writeModerationServiceUnavailable(
	w http.ResponseWriter,
	r *http.Request,
) {
	writeHTTPError(
		w,
		r,
		contentgenerated.AppErrorFromStorageReadFailed(
			"moderation service facades are not configured",
		),
	)
}
