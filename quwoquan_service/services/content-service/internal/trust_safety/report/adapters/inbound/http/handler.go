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
	"quwoquan_service/runtime/operation"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	reporterrors "quwoquan_service/services/content-service/generated/trust_safety/report"
	reportapp "quwoquan_service/services/content-service/internal/trust_safety/report/application"
	reportmodel "quwoquan_service/services/content-service/internal/trust_safety/report/domain/model"
)

// Handler owns Report's public transport contract. The shared Content router
// may dispatch here, but Post must not parse Report wire payloads or invoke the
// aggregate facade directly.
type Handler struct{ service *reportapp.Facades }

func NewHandler(service *reportapp.Facades) *Handler {
	if service == nil {
		panic("Report HTTP handler requires facades")
	}
	return &Handler{service: service}
}

func (h *Handler) Create(w http.ResponseWriter, r *http.Request) {
	var body struct {
		TargetType  reportmodel.TargetType `json:"targetType"`
		TargetID    string                 `json:"targetId"`
		Reason      reportmodel.Reason     `json:"reason"`
		Description string                 `json:"description"`
	}
	if err := decodeStrictJSON(r, &body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"请求体解析失败",
			"CreateReport request body is invalid: "+err.Error(),
		))
		return
	}
	current, ok := operation.FromContext(r.Context())
	reporterID := strings.TrimSpace(current.Actor.PersonaID)
	reporterAccountID := strings.TrimSpace(current.Actor.AccountID)
	if !ok || reporterID == "" || reporterAccountID == "" {
		writeHTTPError(w, r, contentgenerated.AppErrorFromUnauthorized(
			"trusted account and persona actors are required for CreateReport",
		))
		return
	}
	payload, err := h.service.CreateReport(
		r.Context(),
		reportapp.CreateReportCommand{
			ReporterID:        reporterID,
			ReporterAccountID: reporterAccountID,
			TargetType:        body.TargetType,
			TargetID:          body.TargetID,
			Reason:            body.Reason,
			Description:       body.Description,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, payload)
}

func (h *Handler) List(w http.ResponseWriter, r *http.Request) {
	if _, ok := verifiedOperatorAccountID(w, r); !ok {
		return
	}
	limit, ok := parseLimit(w, r)
	if !ok {
		return
	}
	payload, err := h.service.ListReports(
		r.Context(),
		reportapp.ListReportsQuery{Limit: limit},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, payload)
}

func (h *Handler) ListMine(w http.ResponseWriter, r *http.Request) {
	current, ok := operation.FromContext(r.Context())
	reporterID := strings.TrimSpace(current.Actor.PersonaID)
	if !ok || reporterID == "" {
		writeHTTPError(w, r, contentgenerated.AppErrorFromUnauthorized(
			"trusted persona actor is required for ListMyReports",
		))
		return
	}
	limit, ok := parseLimit(w, r)
	if !ok {
		return
	}
	payload, err := h.service.ListMyReports(
		r.Context(),
		reportapp.ListMyReportsQuery{
			ReporterID: reporterID,
			Cursor:     strings.TrimSpace(r.URL.Query().Get("cursor")),
			Limit:      limit,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, payload)
}

func (h *Handler) Get(w http.ResponseWriter, r *http.Request) {
	if _, ok := verifiedOperatorAccountID(w, r); !ok {
		return
	}
	reportID := strings.TrimSpace(r.PathValue("reportId"))
	if reportID == "" {
		writeHTTPError(w, r, contentgenerated.AppErrorFromInvalidArgument(
			"GetReport requires reportId",
		))
		return
	}
	payload, err := h.service.GetReport(
		r.Context(),
		reportapp.GetReportQuery{ReportID: reportID},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, payload)
}

func (h *Handler) BeginReview(w http.ResponseWriter, r *http.Request) {
	operatorAccountID, ok := verifiedOperatorAccountID(w, r)
	if !ok {
		return
	}
	if err := decodeEmptyRequest(r); err != nil {
		writeHTTPError(w, r, contentgenerated.AppErrorFromInvalidArgument(
			"BeginReportReview request body must be empty",
		))
		return
	}
	reportID := strings.TrimSpace(r.PathValue("reportId"))
	if reportID == "" {
		writeHTTPError(w, r, contentgenerated.AppErrorFromInvalidArgument(
			"BeginReportReview requires reportId",
		))
		return
	}
	payload, err := h.service.BeginReview(
		r.Context(),
		reportapp.BeginReviewReportCommand{
			ReportID: reportID, ReviewerID: operatorAccountID,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, payload)
}

func (h *Handler) Dismiss(w http.ResponseWriter, r *http.Request) {
	operatorAccountID, ok := verifiedOperatorAccountID(w, r)
	if !ok {
		return
	}
	if err := decodeEmptyRequest(r); err != nil {
		writeHTTPError(w, r, contentgenerated.AppErrorFromInvalidArgument(
			"DismissReport request body must be empty",
		))
		return
	}
	reportID := strings.TrimSpace(r.PathValue("reportId"))
	if reportID == "" {
		writeHTTPError(w, r, contentgenerated.AppErrorFromInvalidArgument(
			"DismissReport requires reportId",
		))
		return
	}
	payload, err := h.service.Dismiss(
		r.Context(),
		reportapp.DismissReportCommand{
			ReportID: reportID, ReviewerID: operatorAccountID,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, payload)
}

func (h *Handler) Resolve(w http.ResponseWriter, r *http.Request) {
	operatorAccountID, ok := verifiedOperatorAccountID(w, r)
	if !ok {
		return
	}
	var body struct {
		Resolution reportmodel.Resolution `json:"resolution"`
	}
	if err := decodeStrictJSON(r, &body); err != nil {
		writeHTTPError(w, r, contentgenerated.AppErrorFromInvalidArgument(
			"ResolveReport request body is invalid: "+err.Error(),
		))
		return
	}
	reportID := strings.TrimSpace(r.PathValue("reportId"))
	if reportID == "" {
		writeHTTPError(w, r, contentgenerated.AppErrorFromInvalidArgument(
			"ResolveReport requires reportId",
		))
		return
	}
	payload, err := h.service.Resolve(
		r.Context(),
		reportapp.ResolveReportCommand{
			ReportID: reportID, ReviewerID: operatorAccountID,
			Resolution: body.Resolution,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, payload)
}

func (h *Handler) GrantGatheringSafetyTermination(
	w http.ResponseWriter,
	r *http.Request,
) {
	if _, ok := verifiedOperatorAccountID(w, r); !ok {
		return
	}
	var body struct {
		ExpectedReportVersion int64     `json:"expectedReportVersion"`
		ActorPersonaID        string    `json:"actorPersonaId"`
		ExpiresAt             time.Time `json:"expiresAt"`
	}
	if err := decodeStrictJSON(r, &body); err != nil {
		writeHTTPError(w, r, reporterrors.AppErrorFromGatheringSafetyAuthorizationInvalid(
			"GrantGatheringSafetyTermination request body is invalid",
		))
		return
	}
	current, ok := operation.FromContext(r.Context())
	reportID := strings.TrimSpace(r.PathValue("reportId"))
	if !ok || reportID == "" || strings.TrimSpace(current.IdempotencyKey) == "" {
		writeHTTPError(w, r, reporterrors.AppErrorFromGatheringSafetyAuthorizationInvalid(
			"GrantGatheringSafetyTermination context is invalid",
		))
		return
	}
	payload, err := h.service.GrantGatheringSafetyTermination(
		r.Context(),
		reportapp.GrantGatheringSafetyTerminationCommand{
			ReportID:              reportID,
			ExpectedReportVersion: body.ExpectedReportVersion,
			ActorPersonaID:        body.ActorPersonaID,
			ExpiresAt:             body.ExpiresAt,
			IdempotencyKey:        current.IdempotencyKey,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, payload)
}

func (h *Handler) RevokeGatheringSafetyTermination(
	w http.ResponseWriter,
	r *http.Request,
) {
	if _, ok := verifiedOperatorAccountID(w, r); !ok {
		return
	}
	var body struct {
		DecisionRef string `json:"decisionRef"`
	}
	if err := decodeStrictJSON(r, &body); err != nil {
		writeHTTPError(w, r, reporterrors.AppErrorFromGatheringSafetyAuthorizationInvalid(
			"RevokeGatheringSafetyTermination request body is invalid",
		))
		return
	}
	current, ok := operation.FromContext(r.Context())
	reportID := strings.TrimSpace(r.PathValue("reportId"))
	if !ok || reportID == "" || strings.TrimSpace(current.IdempotencyKey) == "" {
		writeHTTPError(w, r, reporterrors.AppErrorFromGatheringSafetyAuthorizationInvalid(
			"RevokeGatheringSafetyTermination context is invalid",
		))
		return
	}
	payload, err := h.service.RevokeGatheringSafetyTermination(
		r.Context(),
		reportapp.RevokeGatheringSafetyTerminationCommand{
			ReportID:       reportID,
			DecisionRef:    body.DecisionRef,
			IdempotencyKey: current.IdempotencyKey,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, payload)
}

func (h *Handler) AuthorizeGatheringSafetyTermination(
	w http.ResponseWriter,
	r *http.Request,
) {
	if !verifiedServicePrincipal(w, r) {
		return
	}
	var body struct {
		ActorPersonaID string `json:"actorPersonaId"`
		GatheringID    string `json:"gatheringId"`
		Action         string `json:"action"`
		EvidenceRef    string `json:"evidenceRef"`
		DecisionRef    string `json:"decisionRef"`
	}
	if err := decodeStrictJSON(r, &body); err != nil {
		writeHTTPError(w, r, reporterrors.AppErrorFromGatheringSafetyAuthorizationInvalid(
			"AuthorizeGatheringSafetyTermination request body is invalid",
		))
		return
	}
	payload, err := h.service.AuthorizeGatheringSafetyTermination(
		r.Context(),
		reportapp.AuthorizeGatheringSafetyTerminationQuery{
			ActorPersonaID: body.ActorPersonaID,
			GatheringID:    body.GatheringID,
			Action:         body.Action,
			EvidenceRef:    body.EvidenceRef,
			DecisionRef:    body.DecisionRef,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, payload)
}

func parseLimit(w http.ResponseWriter, r *http.Request) (int, bool) {
	limit := 20
	if raw := strings.TrimSpace(r.URL.Query().Get("limit")); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed < 1 || parsed > 100 {
			writeHTTPError(w, r, contentgenerated.AppErrorFromInvalidArgument(
				"report limit must be an integer between 1 and 100",
			))
			return 0, false
		}
		limit = parsed
	}
	return limit, true
}

func verifiedOperatorAccountID(w http.ResponseWriter, r *http.Request) (string, bool) {
	principal, principalOK := rtauth.PrincipalFromContext(r.Context())
	descriptor, descriptorOK := rtauth.OperationDescriptorFromContext(r.Context())
	accountID := strings.TrimSpace(principal.Actor.AccountID)
	if principalOK && descriptorOK && accountID != "" &&
		descriptor.Principal == "operator" && descriptor.CommercialStatus == "ready" {
		return accountID, true
	}
	writeHTTPError(w, r, contentgenerated.AppErrorFromUnauthorized(
		"verified ready operator operation principal is required for report operations",
	))
	return "", false
}

func verifiedServicePrincipal(w http.ResponseWriter, r *http.Request) bool {
	principal, principalOK := rtauth.PrincipalFromContext(r.Context())
	descriptor, descriptorOK := rtauth.OperationDescriptorFromContext(r.Context())
	accountID := strings.TrimSpace(principal.Actor.AccountID)
	if principalOK && descriptorOK &&
		strings.HasPrefix(accountID, "service:") &&
		descriptor.Principal == "service" &&
		descriptor.CommercialStatus == "ready" {
		return true
	}
	writeHTTPError(w, r, contentgenerated.AppErrorFromUnauthorized(
		"verified service principal is required for Gathering safety authorization",
	))
	return false
}

func decodeEmptyRequest(r *http.Request) error {
	if r.Body == nil {
		return nil
	}
	var payload struct{}
	err := decodeStrictJSON(r, &payload)
	if err == io.EOF {
		return nil
	}
	return err
}

func decodeStrictJSON(r *http.Request, target any) error {
	if r == nil || r.Body == nil {
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

func writeJSON(w http.ResponseWriter, status int, payload any) {
	httpcodec.WriteJSON(w, status, payload, "report")
}

func writeHTTPError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}
