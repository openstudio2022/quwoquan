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
	if nonPromotableFirstPartyPrevalidation(appEnv) {
		// The application layer maps a nil client to the canonical provider
		// unavailable error. Do not load mTLS material or fall back to a fixture.
		return nil, nil
	}
	return newRemoteOTPExternalInteractionClient(baseURL, appEnv, signer)
}
