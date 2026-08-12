package http

import (
	"net/http"
	"strings"

	sessiongenerated "quwoquan_service/services/user-service/generated/account/account_session"
	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
)

func (h *UserHandler) handleOtpDeliveryReadiness(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, h.auth.GetOtpDeliveryReadiness(r.Context()))
}

func (h *UserHandler) handleSendOtp(w http.ResponseWriter, r *http.Request) {
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	phone := strings.TrimSpace(anyString(body["phone"]))
	deviceID := strings.TrimSpace(anyString(body["deviceId"]))
	platform := strings.TrimSpace(anyString(body["platform"]))
	appVersion := strings.TrimSpace(anyString(body["appVersion"]))
	sourceOperation := strings.TrimSpace(anyString(body["sourceOperation"]))
	bindingTicket := strings.TrimSpace(anyString(body["bindingTicket"]))
	idempotencyKey := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if phone == "" {
		writeInvalidArg(w, r, "phone required")
		return
	}
	if idempotencyKey == "" {
		writeInvalidArg(w, r, "Idempotency-Key required")
		return
	}
	result, err := h.auth.SendOtp(
		r.Context(),
		phone,
		deviceID,
		platform,
		appVersion,
		sourceOperation,
		bindingTicket,
		idempotencyKey,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *UserHandler) handleLoginWithPhone(w http.ResponseWriter, r *http.Request) {
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	phone := strings.TrimSpace(anyString(body["phone"]))
	otpCode := strings.TrimSpace(anyString(body["otpCode"]))
	deviceID := strings.TrimSpace(anyString(body["deviceId"]))
	platform := strings.TrimSpace(anyString(body["platform"]))
	appVersion := strings.TrimSpace(anyString(body["appVersion"]))
	agreementVersion := strings.TrimSpace(anyString(body["agreementVersion"]))
	privacyVersion := strings.TrimSpace(anyString(body["privacyVersion"]))
	if phone == "" {
		writeInvalidArg(w, r, "phone required")
		return
	}
	result, err := h.auth.LoginWithPhone(
		r.Context(),
		phone,
		otpCode,
		"",
		deviceID,
		platform,
		appVersion,
		agreementVersion,
		privacyVersion,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *UserHandler) handleLoginWithWechat(w http.ResponseWriter, r *http.Request) {
	h.handleFederatedLogin(w, r, h.wechatLogin, "wechatCode")
}

func (h *UserHandler) handleLoginWithAlipay(w http.ResponseWriter, r *http.Request) {
	h.handleFederatedLogin(w, r, h.alipayLogin, "alipayAuthCode")
}

func (h *UserHandler) handleLoginWithQq(w http.ResponseWriter, r *http.Request) {
	h.handleFederatedLogin(w, r, h.qqLogin, "qqAuthCode")
}

func (h *UserHandler) handleFederatedLogin(
	w http.ResponseWriter,
	r *http.Request,
	login *application.FederatedLoginFacade,
	primaryField string,
) {
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	authCode := strings.TrimSpace(anyString(body[primaryField]))
	deviceID := strings.TrimSpace(anyString(body["deviceId"]))
	platform := strings.TrimSpace(anyString(body["platform"]))
	appVersion := strings.TrimSpace(anyString(body["appVersion"]))
	agreementVersion := strings.TrimSpace(anyString(body["agreementVersion"]))
	privacyVersion := strings.TrimSpace(anyString(body["privacyVersion"]))
	if authCode == "" {
		writeInvalidArg(w, r, primaryField+" required")
		return
	}
	if login == nil {
		writeHTTPError(
			w,
			r,
			sessiongenerated.AppErrorFromSocialProviderUnavailable(
				"federated identity capability unavailable",
			),
		)
		return
	}
	result, err := login.Login(
		r.Context(),
		authCode,
		deviceID,
		platform,
		appVersion,
		agreementVersion,
		privacyVersion,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *UserHandler) handleOneTapLogin(w http.ResponseWriter, r *http.Request) {
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	carrierToken := strings.TrimSpace(anyString(body["carrierToken"]))
	deviceID := strings.TrimSpace(anyString(body["deviceId"]))
	platform := strings.TrimSpace(anyString(body["platform"]))
	appVersion := strings.TrimSpace(anyString(body["appVersion"]))
	agreementVersion := strings.TrimSpace(anyString(body["agreementVersion"]))
	privacyVersion := strings.TrimSpace(anyString(body["privacyVersion"]))
	if carrierToken == "" {
		writeInvalidArg(w, r, "carrierToken required")
		return
	}
	result, err := h.auth.LoginWithOneTap(
		r.Context(),
		carrierToken,
		deviceID,
		platform,
		appVersion,
		agreementVersion,
		privacyVersion,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *UserHandler) handleOneTapLoginHint(w http.ResponseWriter, r *http.Request) {
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	carrierToken := strings.TrimSpace(anyString(body["carrierToken"]))
	deviceID := strings.TrimSpace(anyString(body["deviceId"]))
	platform := strings.TrimSpace(anyString(body["platform"]))
	appVersion := strings.TrimSpace(anyString(body["appVersion"]))
	if carrierToken == "" {
		writeInvalidArg(w, r, "carrierToken required")
		return
	}
	result, err := h.auth.ResolveOneTapLoginHint(
		r.Context(),
		carrierToken,
		deviceID,
		platform,
		appVersion,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *UserHandler) handleAnonymousLogin(w http.ResponseWriter, r *http.Request) {
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	installID, _ := body["installId"].(string)
	deviceFingerprintHash, _ := body["deviceFingerprintHash"].(string)
	platform, _ := body["platform"].(string)
	appVersion, _ := body["appVersion"].(string)
	if strings.TrimSpace(installID) == "" {
		writeInvalidArg(w, r, "installId required")
		return
	}
	if strings.TrimSpace(deviceFingerprintHash) == "" {
		writeInvalidArg(w, r, "deviceFingerprintHash required")
		return
	}
	result, err := h.auth.LoginAnonymously(
		r.Context(),
		installID,
		deviceFingerprintHash,
		platform,
		appVersion,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *UserHandler) handleRefreshToken(w http.ResponseWriter, r *http.Request) {
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	refreshToken := strings.TrimSpace(anyString(body["refreshToken"]))
	if refreshToken == "" {
		writeInvalidArg(w, r, "refreshToken required")
		return
	}
	result, err := h.auth.RefreshToken(r.Context(), refreshToken)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"accessToken":               result.AccessToken,
		"refreshToken":              result.RefreshToken,
		"sessionRememberTtlSeconds": result.SessionRememberTTLSeconds,
	})
}

func (h *UserHandler) handleLogout(w http.ResponseWriter, r *http.Request) {
	body, _ := readBody(r)
	ownerID := strings.TrimSpace(userIDFromHeader(r))
	refreshToken := strings.TrimSpace(anyString(body["refreshToken"]))
	if err := h.auth.Logout(r.Context(), ownerID, refreshToken); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"revoked": true})
}
