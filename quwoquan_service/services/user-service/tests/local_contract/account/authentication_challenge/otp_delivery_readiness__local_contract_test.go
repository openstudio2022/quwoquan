// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-012
package local_contract

// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-012.t2

import (
	"context"
	"errors"
	"testing"

	accountapp "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
)

type readinessDispatch struct {
	err error
}

func (dispatch *readinessDispatch) SubmitSMSOTP(
	context.Context,
	accountapp.SMSOTPDispatchRequest,
) (accountapp.ExternalInteractionAccepted, error) {
	return accountapp.ExternalInteractionAccepted{}, nil
}

func (dispatch *readinessDispatch) CheckSMSOTPReadiness(context.Context) error {
	return dispatch.err
}

func TestOtpDeliveryReadinessOnlyReturnsBoundedBusinessState(t *testing.T) {
	ready := accountapp.NewAuthService(nil, nil, nil, nil, nil,
		accountapp.WithExternalInteractionClient(&readinessDispatch{}),
	).GetOtpDeliveryReadiness(context.Background())
	if ready.Availability != "ready" || ready.RetryAfterSeconds != 0 {
		t.Fatalf("ready result = %+v", ready)
	}

	unavailable := accountapp.NewAuthService(nil, nil, nil, nil, nil,
		accountapp.WithExternalInteractionClient(&readinessDispatch{
			err: errors.New("provider body and topology must not escape"),
		}),
	).GetOtpDeliveryReadiness(context.Background())
	if unavailable.Availability != "temporarily_unavailable" || unavailable.RetryAfterSeconds != 5 {
		t.Fatalf("unavailable result = %+v", unavailable)
	}
}

func TestOtpDeliveryReadinessFailsClosedWithoutExplicitChecker(t *testing.T) {
	result := accountapp.NewAuthService(nil, nil, nil, nil, nil).
		GetOtpDeliveryReadiness(context.Background())
	if result.Availability != "temporarily_unavailable" || result.RetryAfterSeconds <= 0 {
		t.Fatalf("missing checker result = %+v", result)
	}
}
