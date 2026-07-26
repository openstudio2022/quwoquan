package main

import (
	"fmt"
	"os"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	userintegration "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/integration"
)

const (
	otpModeFixedTest = "fixed_test"
	otpModeProvider  = "provider"
)

func otpCodeGeneratorForEnvironment(appEnv string) (func() (string, error), error) {
	env := strings.ToLower(strings.TrimSpace(appEnv))
	mode := configuredOTPMode(env)
	return otpCodeGeneratorForMode(env, mode)
}

func configuredOTPMode(env string, configured ...string) string {
	mode := strings.ToLower(strings.TrimSpace(os.Getenv("USER_AUTH_OTP_MODE")))
	if mode == "" && len(configured) > 0 {
		mode = strings.ToLower(strings.TrimSpace(configured[0]))
	}
	if mode == "" {
		if env == "prod" {
			mode = otpModeProvider
		} else {
			mode = otpModeFixedTest
		}
	}
	return mode
}

func otpCodeGeneratorForMode(env, mode string) (func() (string, error), error) {
	switch mode {
	case otpModeFixedTest:
		if env == "prod" {
			return nil, fmt.Errorf("USER_AUTH_OTP_MODE=fixed_test is forbidden in prod")
		}
		return nonProductionFixedOTPGenerator()
	case otpModeProvider:
		return application.GenerateSecureOTPCode, nil
	default:
		return nil, fmt.Errorf("USER_AUTH_OTP_MODE must be fixed_test or provider")
	}
}

func newRemoteOTPExternalInteractionClient(
	baseURL string,
	appEnv string,
	signer *rtauth.Signer,
) (application.ExternalInteractionClient, error) {
	client, err := userintegration.NewIntegrationServiceMTLSClient(3 * time.Second)
	if err != nil {
		return nil, err
	}
	return userintegration.NewExternalInteractionClient(baseURL, appEnv, client, signer)
}
