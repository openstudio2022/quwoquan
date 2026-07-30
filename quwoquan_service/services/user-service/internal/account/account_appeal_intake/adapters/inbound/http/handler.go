package http

import (
	"encoding/json"
	"errors"
	"io"
	stdhttp "net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	usergenerated "quwoquan_service/services/user-service/generated/account/user_account"
	"quwoquan_service/services/user-service/internal/account/account_appeal_intake/application"
)

const (
	IssueCredentialPath  = "/account-appeals/credentials"
	SubmitIntakePath     = "/account-appeals/intakes"
	ClaimIntakePath      = "/internal/user/account-appeal-intakes/{intakeRef}:claim"
	claimIntakeMuxPath   = "/internal/user/account-appeal-intakes/{intakeRefAndAction}"
	claimOperationID     = "user.account_appeal_intake.ClaimAccountAppealIntake"
	claimOwnershipPolicy = "product_ops_account_appeal_claim_only"
	maxRequestBytes      = 4096
)

type Handler struct {
	facade *application.CommandFacade
}

func NewHandler(facade *application.CommandFacade) (*Handler, error) {
	if facade == nil {
		return nil, errors.New("AccountAppealIntake command facade is required")
	}
	return &Handler{facade: facade}, nil
}

func (handler *Handler) RegisterRoutes(mux *stdhttp.ServeMux) {
	mux.HandleFunc("POST "+IssueCredentialPath, handler.issueCredential)
	mux.HandleFunc("POST "+SubmitIntakePath, handler.submitIntake)
	// net/http ServeMux does not accept a literal suffix after a wildcard.
	// Register the whole final segment and reject anything except the canonical
	// ContractGraph `:claim` suffix in the owner handler.
	mux.HandleFunc("POST "+claimIntakeMuxPath, handler.claimIntake)
}

type issueCredentialRequest struct {
	Phone       string `json:"phone"`
	OTPCode     string `json:"otpCode"`
	ChallengeID string `json:"challengeId"`
}

func (handler *Handler) issueCredential(w stdhttp.ResponseWriter, r *stdhttp.Request) {
	var body issueCredentialRequest
	if err := decodeOneObject(w, r, &body); err != nil {
		writeError(w, r, err)
		return
	}
	result, err := handler.facade.IssueCredential(r.Context(), application.IssueCredentialCommand{
		Phone: strings.TrimSpace(body.Phone), OTPCode: []byte(strings.TrimSpace(body.OTPCode)),
		ChallengeID: strings.TrimSpace(body.ChallengeID),
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	w.Header().Set("Cache-Control", "no-store")
	writeJSON(w, stdhttp.StatusCreated, result)
}

type submitIntakeRequest struct {
	AppealCredential string `json:"appealCredential"`
}

func (handler *Handler) submitIntake(w stdhttp.ResponseWriter, r *stdhttp.Request) {
	var body submitIntakeRequest
	if err := decodeOneObject(w, r, &body); err != nil {
		writeError(w, r, err)
		return
	}
	result, err := handler.facade.SubmitIntake(r.Context(), application.SubmitIntakeCommand{
		AppealCredential: strings.TrimSpace(body.AppealCredential),
		IdempotencyKey:   strings.TrimSpace(r.Header.Get("Idempotency-Key")),
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	w.Header().Set("Cache-Control", "no-store")
	writeJSON(w, stdhttp.StatusCreated, result)
}

type claimIntakeRequest struct {
	AccountID string `json:"accountId"`
	CaseID    string `json:"caseId"`
}

func (handler *Handler) claimIntake(w stdhttp.ResponseWriter, r *stdhttp.Request) {
	invocation, hasInvocation := operation.FromContext(r.Context())
	descriptor, hasDescriptor := rtauth.OperationDescriptorFromContext(r.Context())
	principal, hasPrincipal := rtauth.PrincipalFromContext(r.Context())
	if !hasInvocation || invocation.OperationID != claimOperationID ||
		!hasDescriptor || descriptor.CanonicalOperationID != claimOperationID ||
		descriptor.OwnershipPolicy != claimOwnershipPolicy ||
		strings.TrimSpace(invocation.IdempotencyKey) == "" || !hasPrincipal {
		writeError(w, r, usergenerated.AppErrorFromUnauthorized(
			"trusted account appeal claim operation context is required",
		))
		return
	}
	if strings.TrimSpace(principal.Actor.AccountID) != "service:product-ops-service" {
		writeError(w, r, usergenerated.AppErrorFromForbidden(
			"only product-ops-service may claim an account appeal intake",
		))
		return
	}
	intakeRefAndAction := strings.TrimSpace(r.PathValue("intakeRefAndAction"))
	if !strings.HasSuffix(intakeRefAndAction, ":claim") {
		writeError(w, r, invalidRequestError("invalid account appeal claim path"))
		return
	}
	intakeRef := strings.TrimSuffix(intakeRefAndAction, ":claim")
	var body claimIntakeRequest
	if err := decodeOneObject(w, r, &body); err != nil {
		writeError(w, r, err)
		return
	}
	result, err := handler.facade.ClaimIntake(r.Context(), application.ClaimIntakeCommand{
		IntakeRef: strings.TrimSpace(intakeRef),
		AccountID: strings.TrimSpace(body.AccountID),
		CaseID:    strings.TrimSpace(body.CaseID),
		IdempotencyKey: strings.TrimSpace(
			r.Header.Get("Idempotency-Key"),
		),
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	w.Header().Set("Cache-Control", "no-store")
	writeJSON(w, stdhttp.StatusOK, result)
}

func decodeOneObject(w stdhttp.ResponseWriter, r *stdhttp.Request, target any) error {
	r.Body = stdhttp.MaxBytesReader(w, r.Body, maxRequestBytes)
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return invalidRequestError("invalid account appeal request body")
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return invalidRequestError("account appeal request must contain one object")
	}
	return nil
}

func invalidRequestError(debugMessage string) error {
	return usergenerated.AppErrorFromInvalidArgument(debugMessage)
}

func writeJSON(w stdhttp.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeError(w stdhttp.ResponseWriter, r *stdhttp.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}
