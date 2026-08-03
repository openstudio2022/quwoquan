package http

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	httpcodec "quwoquan_service/runtime/httpcodec"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	moderationapp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/application"
	moderationmodel "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/domain/model"
)

type Handler struct{ service *moderationapp.Facades }

func NewHandler(service *moderationapp.Facades) *Handler {
	if service == nil {
		panic("PostModerationCase HTTP handler requires facades")
	}
	return &Handler{service: service}
}

// PostModerationCase 的 internal transport 装配。auth/scope/token 由 route
// guard（generated operation descriptor）先行执行；operator 命令在此再做
// principal 二次校验（与 report 队列同源的双保险，客户端 guard 不是安全边界）。

func (h *Handler) Open(w http.ResponseWriter, r *http.Request) {
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
	result, err := h.service.OpenPostModerationCase(
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
	writeJSON(w, http.StatusOK, commandResponseFrom(result))
}

func (h *Handler) Review(w http.ResponseWriter, r *http.Request) {
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
	result, err := h.service.ReviewPostModerationCase(
		r.Context(),
		moderationapp.ReviewPostModerationCaseCommand{
			PostID:     strings.TrimSpace(r.PathValue("postId")),
			CaseID:     body.CaseID,
			ReviewerID: reviewerID,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, commandResponseFrom(result))
}

func (h *Handler) Decide(w http.ResponseWriter, r *http.Request) {
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
	result, err := h.service.DecidePostModerationCase(
		r.Context(),
		moderationapp.DecidePostModerationCaseCommand{
			PostID:         strings.TrimSpace(r.PathValue("postId")),
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
	writeJSON(w, http.StatusOK, commandResponseFrom(result))
}

func (h *Handler) Supersede(w http.ResponseWriter, r *http.Request) {
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
	result, err := h.service.SupersedePostModerationCase(
		r.Context(),
		moderationapp.SupersedePostModerationCaseCommand{
			PostID: strings.TrimSpace(r.PathValue("postId")),
			CaseID: body.CaseID,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, commandResponseFrom(result))
}

func (h *Handler) GetCurrent(
	w http.ResponseWriter,
	r *http.Request,
) {
	if _, ok := verifiedModerationOperatorAccountID(w, r); !ok {
		return
	}
	postID := strings.TrimSpace(r.PathValue("postId"))
	result, err := h.service.GetCurrentPostModerationCase(
		r.Context(),
		moderationapp.GetCurrentPostModerationCaseQuery{PostID: postID},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) GetPublicationEligibility(w http.ResponseWriter, r *http.Request) {
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
	slice, err := h.service.GetPostPublicationEligibility(
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
	writeJSON(w, http.StatusOK, eligibilityResponseFrom(slice))
}

type commandResponse struct {
	CaseID   string                 `json:"caseId"`
	Version  int64                  `json:"version"`
	Status   moderationmodel.Status `json:"status"`
	Replayed bool                   `json:"replayed"`
}

func commandResponseFrom(result moderationapp.PostModerationCaseCommandResult) commandResponse {
	return commandResponse{
		CaseID: result.CaseID, Version: result.Version,
		Status: result.Status, Replayed: result.Replayed,
	}
}

type eligibilityResponse struct {
	Eligible      bool                   `json:"eligible"`
	CaseID        string                 `json:"caseId,omitempty"`
	CaseVersion   int64                  `json:"caseVersion,omitempty"`
	Moderation    moderationmodel.Status `json:"moderation,omitempty"`
	CheckedAt     time.Time              `json:"checkedAt"`
	DecisionAt    *time.Time             `json:"decisionAt,omitempty"`
	FailureReason string                 `json:"failureReason,omitempty"`
}

func eligibilityResponseFrom(value moderationapp.PublicationEligibilitySlice) eligibilityResponse {
	return eligibilityResponse{
		Eligible: value.Eligible, CaseID: value.CaseID, CaseVersion: value.CaseVersion,
		Moderation: value.Moderation, CheckedAt: value.CheckedAt,
		DecisionAt: value.DecisionAt, FailureReason: value.FailureReason,
	}
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

func decodeStrictReportJSON(request *http.Request, target any) error {
	if request.Body == nil {
		return io.EOF
	}
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "请求体包含多个 JSON 值", "moderation request contains multiple JSON values")
		}
		return err
	}
	return nil
}

func writeJSON(writer http.ResponseWriter, status int, value any) {
	httpcodec.WriteJSON(writer, status, value, "post_moderation_case")
}

func writeHTTPError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
