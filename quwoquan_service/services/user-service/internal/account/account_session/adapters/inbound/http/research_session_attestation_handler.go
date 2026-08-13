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

const (
	ResearchSessionAttestationPath    = "/auth/research/session/attestation"
	ResearchIdentityAttestationHeader = "X-Research-Identity-Attestation"
)

type ResearchSessionAttestationHandler struct {
	facade *sessionapp.ResearchSessionQueryFacade
}

func NewResearchSessionAttestationHandler(
	facade *sessionapp.ResearchSessionQueryFacade,
) (*ResearchSessionAttestationHandler, error) {
	if facade == nil {
		return nil, errors.New("research identity query facade is required")
	}
	return &ResearchSessionAttestationHandler{facade: facade}, nil
}

func (handler *ResearchSessionAttestationHandler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET "+ResearchSessionAttestationPath, handler.get)
}

func RegisterResearchSessionAttestationRoutes(
	mux *http.ServeMux,
	handler *ResearchSessionAttestationHandler,
) {
	handler.RegisterRoutes(mux)
}

func (handler *ResearchSessionAttestationHandler) get(
	w http.ResponseWriter,
	r *http.Request,
) {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok || principal.Actor.AccountID == "" {
		runtimeerrors.WriteHTTPError(w, usergenerated.AppErrorFromUnauthorized(
			"research identity readback requires a verified account principal",
		), runtimeerrors.HTTPWriteOptionsFromRequest(r))
		return
	}
	result, err := handler.facade.GetResearchSessionAttestation(
		r.Context(),
		principal.Actor.AccountID,
		r.Header.Get(ResearchIdentityAttestationHeader),
	)
	if err != nil {
		switch {
		case errors.Is(err, sessionapp.ErrResearchIdentityInvalid):
			err = sessiongenerated.AppErrorFromResearchIdentityInvalid(
				"research identity attestation is invalid or expired",
			)
		default:
			err = sessiongenerated.AppErrorFromAccountSecurityUnavailable(
				"research identity readback is unavailable",
			)
		}
		runtimeerrors.WriteHTTPError(w, err, runtimeerrors.HTTPWriteOptionsFromRequest(r))
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(result)
}
