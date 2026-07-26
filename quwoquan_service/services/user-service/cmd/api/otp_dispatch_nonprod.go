//go:build nonprod

package main

import (
	"context"
	"fmt"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
)

type fixedOTPDispatchClient struct{}

func (fixedOTPDispatchClient) SubmitSMSOTP(
	_ context.Context,
	req application.SMSOTPDispatchRequest,
) (application.ExternalInteractionAccepted, error) {
	if strings.TrimSpace(req.RequestID) == "" ||
		strings.TrimSpace(req.ChallengeID) == "" ||
		strings.TrimSpace(req.CodeRef) == "" {
		return application.ExternalInteractionAccepted{}, fmt.Errorf("fixed OTP challenge reference is incomplete")
	}
	return application.ExternalInteractionAccepted{
		RequestID: req.RequestID,
		Status:    "accepted",
	}, nil
}

func otpExternalInteractionClientForEnvironment(
	appEnv string,
	mode string,
	baseURL string,
	signer *rtauth.Signer,
) (application.ExternalInteractionClient, error) {
	if mode == otpModeFixedTest {
		return fixedOTPDispatchClient{}, nil
	}
	return newRemoteOTPExternalInteractionClient(baseURL, appEnv, signer)
}
