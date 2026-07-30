package http

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/user-service/generated/account/user_account"
	bindingapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
)

type FederatedPhoneBindingHandler struct {
	completer bindingapp.FederatedPhoneBindingCompleter
}

func NewFederatedPhoneBindingHandler(
	completer bindingapp.FederatedPhoneBindingCompleter,
) (*FederatedPhoneBindingHandler, error) {
	if completer == nil {
		return nil, errors.New("federated phone binding completer is required")
	}
	return &FederatedPhoneBindingHandler{completer: completer}, nil
}

func (handler *FederatedPhoneBindingHandler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc(
		"POST /auth/login/social/phone/complete",
		handler.complete,
	)
}

func (handler *FederatedPhoneBindingHandler) complete(
	w http.ResponseWriter,
	r *http.Request,
) {
	var command struct {
		BindingTicket    string `json:"bindingTicket"`
		Phone            string `json:"phone"`
		OTPCode          string `json:"otpCode"`
		ChallengeID      string `json:"challengeId"`
		DeviceID         string `json:"deviceId"`
		Platform         string `json:"platform"`
		AppVersion       string `json:"appVersion"`
		AgreementVersion string `json:"agreementVersion"`
		PrivacyVersion   string `json:"privacyVersion"`
	}
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 64<<10))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&command); err != nil {
		writeFederatedBindingError(
			w,
			r,
			generated.AppErrorFromInvalidArgument("invalid request body"),
		)
		return
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		writeFederatedBindingError(
			w,
			r,
			generated.AppErrorFromInvalidArgument("request body must contain one object"),
		)
		return
	}
	result, err := handler.completer.CompleteFederatedPhoneBinding(
		r.Context(),
		bindingapp.CompleteFederatedPhoneBindingCommand{
			BindingTicket:    strings.TrimSpace(command.BindingTicket),
			Phone:            strings.TrimSpace(command.Phone),
			OTPCode:          strings.TrimSpace(command.OTPCode),
			ChallengeID:      strings.TrimSpace(command.ChallengeID),
			DeviceID:         strings.TrimSpace(command.DeviceID),
			Platform:         strings.TrimSpace(command.Platform),
			AppVersion:       strings.TrimSpace(command.AppVersion),
			AgreementVersion: strings.TrimSpace(command.AgreementVersion),
			PrivacyVersion:   strings.TrimSpace(command.PrivacyVersion),
		},
	)
	if err != nil {
		writeFederatedBindingError(w, r, err)
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(result)
}

func writeFederatedBindingError(
	w http.ResponseWriter,
	r *http.Request,
	err error,
) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}
