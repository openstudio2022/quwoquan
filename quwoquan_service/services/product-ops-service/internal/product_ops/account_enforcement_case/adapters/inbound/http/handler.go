package http

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/product-ops-service/generated/product_ops/account_enforcement_case"
	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/application"
	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/domain/model"
)

const caseRoutePrefix = "/control-plane/product/account-enforcement-cases/"

type Handler struct {
	service *application.Service
}

func NewHandler(service *application.Service) *Handler {
	if service == nil {
		panic("AccountEnforcementCase HTTP handler requires a service")
	}
	return &Handler{service: service}
}

func (handler *Handler) Register(mux *http.ServeMux) {
	if mux == nil {
		panic("AccountEnforcementCase HTTP handler requires a mux")
	}
	mux.Handle(caseRoutePrefix, handler)
}

func (handler *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	suffix := strings.TrimPrefix(r.URL.Path, caseRoutePrefix)
	switch {
	case r.Method == http.MethodPost && suffix == "moderation":
		handler.openModeration(w, r)
	case r.Method == http.MethodPost && suffix == "appeal":
		handler.openAppeal(w, r)
	case r.Method == http.MethodPost && strings.HasSuffix(suffix, ":review"):
		handler.review(w, r, strings.TrimSuffix(suffix, ":review"))
	case r.Method == http.MethodPost && strings.HasSuffix(suffix, ":retry-delivery"):
		handler.retryDelivery(w, r, strings.TrimSuffix(suffix, ":retry-delivery"))
	case r.Method == http.MethodGet && suffix != "" && !strings.Contains(suffix, "/"):
		handler.get(w, r, suffix)
	default:
		writeError(w, r, generated.AppErrorFromAccountEnforcementCaseInvalidArgument(
			"account enforcement route or method is not registered",
		))
	}
}

type openModerationRequest struct {
	CaseID       string   `json:"caseId"`
	AccountID    string   `json:"accountId"`
	PolicyRef    string   `json:"policyRef"`
	EvidenceRefs []string `json:"evidenceRefs"`
}

func (handler *Handler) openModeration(w http.ResponseWriter, r *http.Request) {
	actorID, ok := verifiedActor(r)
	if !ok {
		writeError(w, r, generated.AppErrorFromAccountEnforcementCaseInvalidArgument(
			"verified operator principal is required",
		))
		return
	}
	var request openModerationRequest
	if err := decodeStrictJSON(r, &request); err != nil {
		writeError(w, r, generated.AppErrorFromAccountEnforcementCaseInvalidArgument(
			"invalid moderation case request",
		))
		return
	}
	result, err := handler.service.OpenModeration(r.Context(), application.OpenModerationCommand{
		CaseID: request.CaseID, AccountID: request.AccountID, PolicyRef: request.PolicyRef,
		EvidenceRefs: request.EvidenceRefs, ActorID: actorID,
		IdempotencyKey: strings.TrimSpace(r.Header.Get("Idempotency-Key")),
	})
	if err != nil {
		writeApplicationError(w, r, err, true)
		return
	}
	writeJSON(w, http.StatusCreated, result)
}

type openAppealRequest struct {
	CaseID           string   `json:"caseId"`
	AccountID        string   `json:"accountId"`
	SourceDecisionID string   `json:"sourceDecisionId"`
	IntakeRef        string   `json:"intakeRef"`
	EvidenceRefs     []string `json:"evidenceRefs"`
}

func (handler *Handler) openAppeal(w http.ResponseWriter, r *http.Request) {
	actorID, ok := verifiedActor(r)
	if !ok {
		writeError(w, r, generated.AppErrorFromAccountEnforcementCaseInvalidArgument(
			"verified operator principal is required",
		))
		return
	}
	var request openAppealRequest
	if err := decodeStrictJSON(r, &request); err != nil {
		writeError(w, r, generated.AppErrorFromAccountEnforcementCaseInvalidArgument(
			"invalid appeal case request",
		))
		return
	}
	result, err := handler.service.OpenAppeal(r.Context(), application.OpenAppealCommand{
		CaseID: request.CaseID, AccountID: request.AccountID,
		SourceDecisionID: request.SourceDecisionID, IntakeRef: request.IntakeRef,
		EvidenceRefs: request.EvidenceRefs, ActorID: actorID,
		IdempotencyKey: strings.TrimSpace(r.Header.Get("Idempotency-Key")),
	})
	if err != nil {
		writeApplicationError(w, r, err, true)
		return
	}
	writeJSON(w, http.StatusCreated, result)
}

type reviewRequest struct {
	Verdict model.ReviewVerdict `json:"verdict"`
}

func (handler *Handler) review(w http.ResponseWriter, r *http.Request, caseID string) {
	actorID, ok := verifiedActor(r)
	if !ok {
		writeError(w, r, generated.AppErrorFromAccountEnforcementCaseInvalidArgument(
			"verified operator principal is required",
		))
		return
	}
	var request reviewRequest
	if err := decodeStrictJSON(r, &request); err != nil {
		writeError(w, r, generated.AppErrorFromAccountEnforcementCaseInvalidArgument(
			"invalid account enforcement review",
		))
		return
	}
	result, err := handler.service.Review(r.Context(), application.ReviewCommand{
		CaseID: caseID, Verdict: request.Verdict, ActorID: actorID,
		IdempotencyKey: strings.TrimSpace(r.Header.Get("Idempotency-Key")),
	})
	if err != nil {
		writeApplicationError(w, r, err, true)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (handler *Handler) retryDelivery(w http.ResponseWriter, r *http.Request, caseID string) {
	actorID, ok := verifiedActor(r)
	if !ok {
		writeError(w, r, generated.AppErrorFromAccountEnforcementCaseInvalidArgument(
			"verified operator principal is required",
		))
		return
	}
	if err := requireEmptyBody(r); err != nil {
		writeError(w, r, generated.AppErrorFromAccountEnforcementCaseInvalidArgument(
			"retry delivery body must be empty",
		))
		return
	}
	result, err := handler.service.RetryDelivery(r.Context(), application.RetryDeliveryCommand{
		CaseID: caseID, ActorID: actorID,
		IdempotencyKey: strings.TrimSpace(r.Header.Get("Idempotency-Key")),
	})
	if err != nil {
		writeApplicationError(w, r, err, true)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (handler *Handler) get(w http.ResponseWriter, r *http.Request, caseID string) {
	if _, ok := verifiedActor(r); !ok {
		writeError(w, r, generated.AppErrorFromAccountEnforcementCaseInvalidArgument(
			"verified operator principal is required",
		))
		return
	}
	result, err := handler.service.Get(r.Context(), caseID)
	if err != nil {
		writeApplicationError(w, r, err, false)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

// verifiedActor only extracts the immutable actor identity established by the
// auth middleware. Principal role and operation scope are enforced once by the
// generated composition guard before this handler is invoked.
func verifiedActor(r *http.Request) (string, bool) {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		return "", false
	}
	actorID := strings.TrimSpace(principal.Actor.AccountID)
	if actorID == "" {
		return "", false
	}
	return actorID, true
}

func decodeStrictJSON(r *http.Request, target any) error {
	if r == nil || r.Body == nil {
		return errors.New("request body is required")
	}
	decoder := json.NewDecoder(io.LimitReader(r.Body, 32768))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return errors.New("request body must contain exactly one object")
	}
	return nil
}

func requireEmptyBody(r *http.Request) error {
	if r == nil || r.Body == nil {
		return nil
	}
	payload, err := io.ReadAll(io.LimitReader(r.Body, 2))
	if err != nil {
		return err
	}
	if strings.TrimSpace(string(payload)) != "" {
		return errors.New("request body must be empty")
	}
	return nil
}

func writeApplicationError(w http.ResponseWriter, r *http.Request, err error, write bool) {
	switch {
	case errors.Is(err, model.ErrInvalidArgument):
		writeError(w, r, generated.AppErrorFromAccountEnforcementCaseInvalidArgument(err.Error()))
	case errors.Is(err, model.ErrCaseNotFound):
		writeError(w, r, generated.AppErrorFromAccountEnforcementCaseNotFound(err.Error()))
	case errors.Is(err, model.ErrIdempotencyConflict):
		writeError(w, r, generated.AppErrorFromAccountEnforcementIdempotencyConflict(err.Error()))
	case errors.Is(err, model.ErrCaseClosed):
		writeError(w, r, generated.AppErrorFromAccountEnforcementCaseClosed(err.Error()))
	case errors.Is(err, model.ErrReviewConflict):
		writeError(w, r, generated.AppErrorFromAccountEnforcementReviewConflict(err.Error()))
	case errors.Is(err, model.ErrSourceDecisionConflict),
		errors.Is(err, model.ErrDeliveryNotRecoverable):
		writeError(w, r, generated.AppErrorFromAccountEnforcementSourceDecisionConflict(err.Error()))
	default:
		if write {
			writeError(w, r, generated.AppErrorFromAccountEnforcementCaseStorageWriteFailed("account enforcement write failed"))
			return
		}
		writeError(w, r, generated.AppErrorFromAccountEnforcementCaseStorageReadFailed("account enforcement read failed"))
	}
}

func writeError(w http.ResponseWriter, r *http.Request, err *rterr.AppError) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
