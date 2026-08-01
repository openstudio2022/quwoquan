package http

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"time"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	consenterrors "quwoquan_service/services/assistant-service/generated/assistant/skill_consent"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_consent/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/model"
)

const (
	grantOperation  = "assistant.skill_consent.GrantSkillConsent"
	revokeOperation = "assistant.skill_consent.RevokeSkillConsent"
	listOperation   = "assistant.skill_consent.ListConsents"
)

type Handler struct {
	commands *application.CommandFacade
	queries  *application.QueryFacade
}

func NewHandler(
	commands *application.CommandFacade,
	queries *application.QueryFacade,
) *Handler {
	return &Handler{commands: commands, queries: queries}
}

func (handler *Handler) RegisterRoutes(mux *http.ServeMux) {
	grant := mustOperationDescriptor(grantOperation)
	revoke := mustOperationDescriptor(revokeOperation)
	list := mustOperationDescriptor(listOperation)
	mux.HandleFunc(grant.Method+" "+grant.PathTemplate, handler.handleGrant)
	mux.HandleFunc(revoke.Method+" "+revoke.PathTemplate, handler.handleRevoke)
	mux.HandleFunc(list.Method+" "+list.PathTemplate, handler.handleList)
}

func (handler *Handler) handleList(writer http.ResponseWriter, request *http.Request) {
	accountID, err := requireVerifiedAccount(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	items, err := handler.queries.List(request.Context(), accountID)
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err))
		return
	}
	views := make([]consentView, 0, len(items))
	for _, item := range items {
		views = append(views, newConsentView(item))
	}
	writeJSON(writer, http.StatusOK, map[string]any{"items": views})
}

func (handler *Handler) handleGrant(writer http.ResponseWriter, request *http.Request) {
	accountID, err := requireVerifiedAccount(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	var body struct {
		GrantedScope string `json:"grantedScope"`
	}
	decoder := json.NewDecoder(http.MaxBytesReader(writer, request.Body, 64<<10))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil && !errors.Is(err, io.EOF) {
		writeHTTPError(
			writer,
			request,
			consenterrors.AppErrorFromConsentInvalidArgument(err.Error()),
		)
		return
	}
	result, err := handler.commands.Grant(
		request.Context(),
		strings.TrimSpace(request.Header.Get("Idempotency-Key")),
		accountID,
		strings.TrimSpace(request.PathValue("skillId")),
		strings.TrimSpace(body.GrantedScope),
	)
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err))
		return
	}
	if result.Consent == nil || !result.Consent.IsGranted() {
		writeHTTPError(
			writer,
			request,
			consenterrors.AppErrorFromConsentUnavailable(
				"grant command returned no active consent",
			),
		)
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"consent":  newConsentView(*result.Consent),
		"replayed": result.Replayed,
	})
}

func (handler *Handler) handleRevoke(writer http.ResponseWriter, request *http.Request) {
	accountID, err := requireVerifiedAccount(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	result, err := handler.commands.Revoke(
		request.Context(),
		strings.TrimSpace(request.Header.Get("Idempotency-Key")),
		accountID,
		strings.TrimSpace(request.PathValue("skillId")),
	)
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err))
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"status":   "ok",
		"skillId":  strings.TrimSpace(request.PathValue("skillId")),
		"replayed": result.Replayed,
	})
}

type consentView struct {
	ID           string     `json:"id"`
	AccountID    string     `json:"accountId"`
	SkillID      string     `json:"skillId"`
	GrantedScope string     `json:"grantedScope"`
	GrantedAt    time.Time  `json:"grantedAt"`
	RevokedAt    *time.Time `json:"revokedAt,omitempty"`
	Granted      bool       `json:"granted"`
}

func newConsentView(consent model.Consent) consentView {
	return consentView{
		ID:           consent.ID,
		AccountID:    consent.AccountID,
		SkillID:      consent.SkillID,
		GrantedScope: consent.GrantedScope,
		GrantedAt:    consent.GrantedAt,
		RevokedAt:    consent.RevokedAt,
		Granted:      consent.IsGranted(),
	}
}

func requireVerifiedAccount(request *http.Request) (string, error) {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if ok && strings.TrimSpace(principal.Actor.AccountID) != "" {
		return strings.TrimSpace(principal.Actor.AccountID), nil
	}
	return "", consenterrors.AppErrorFromConsentUnauthorized(
		"skill consent requires a verified account principal",
	)
}

func mapDomainError(err error) error {
	switch {
	case errors.Is(err, model.ErrInvalidArgument):
		return consenterrors.AppErrorFromConsentInvalidArgument(err.Error())
	case errors.Is(err, model.ErrIdempotencyConflict):
		return consenterrors.AppErrorFromConsentIdempotencyConflict(err.Error())
	case errors.Is(err, model.ErrStorageUnavailable):
		return consenterrors.AppErrorFromConsentUnavailable(err.Error())
	default:
		var appError *rterr.AppError
		if errors.As(err, &appError) {
			return err
		}
		return consenterrors.AppErrorFromConsentUnavailable(err.Error())
	}
}

func mustOperationDescriptor(
	canonicalOperationID string,
) rtauth.OperationSecurityDescriptor {
	for _, descriptor := range operationsecurity.ForDomain("assistant") {
		if descriptor.CanonicalOperationID == canonicalOperationID {
			return descriptor
		}
	}
	panic("missing generated operation descriptor: " + canonicalOperationID)
}

func writeJSON(writer http.ResponseWriter, status int, payload any) {
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(payload)
}

func writeHTTPError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
