//go:build !nonprod

package main

import (
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
)

func otpExternalInteractionClientForEnvironment(
	appEnv string,
	mode string,
	baseURL string,
	signer *rtauth.Signer,
) (application.ExternalInteractionClient, error) {
	if _, err := otpCodeGeneratorForMode(appEnv, mode); err != nil {
		return nil, err
	}
	return newRemoteOTPExternalInteractionClient(baseURL, appEnv, signer)
}
