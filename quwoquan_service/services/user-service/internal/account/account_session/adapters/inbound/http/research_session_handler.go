package http

import (
	"encoding/json"
	"errors"
	"net/http"

	rtauth "quwoquan_service/runtime/auth"
	runtimeerrors "quwoquan_service/runtime/errors"
	sessiongenerated "quwoquan_service/services/user-service/generated/account/account_session"
	usergenerated "quwoquan_service/services/user-service/generated/account/user_account"
	sessionapp "quwoquan_service/services/user-service/internal/account/account_session/application"
)

const ResearchSessionPath = "/auth/research/session"

type ResearchSessionHandler struct {
	facade *sessionapp.ResearchSessionCommandFacade
}

func NewResearchSessionHandler(
	facade *sessionapp.ResearchSessionCommandFacade,
) (*ResearchSessionHandler, error) {
	if facade == nil {
		return nil, errors.New("research identity command facade is required")
	}
	return &ResearchSessionHandler{facade: facade}, nil
}

func (handler *ResearchSessionHandler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST "+ResearchSessionPath, handler.issue)
}

func RegisterResearchSessionRoutes(mux *http.ServeMux, handler *ResearchSessionHandler) {
	handler.RegisterRoutes(mux)
}

func (handler *ResearchSessionHandler) issue(w http.ResponseWriter, r *http.Request) {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok || principal.Actor.AccountID == "" {
		runtimeerrors.WriteHTTPError(w, usergenerated.AppErrorFromUnauthorized(
			"research identity requires a verified account principal",
		), runtimeerrors.HTTPWriteOptionsFromRequest(r))
		return
	}
	result, err := handler.facade.IssueWhitelistedResearchSession(
		r.Context(),
		principal.Actor.AccountID,
	)
	if err != nil {
		switch {
		case errors.Is(err, sessionapp.ErrResearchIdentityForbidden):
			err = usergenerated.AppErrorFromForbidden(
				"research identity account is not allowlisted",
			)
		default:
			err = sessiongenerated.AppErrorFromAccountSecurityUnavailable(
				"research identity issuance is unavailable",
			)
		}
		runtimeerrors.WriteHTTPError(w, err, runtimeerrors.HTTPWriteOptionsFromRequest(r))
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(result)
}
