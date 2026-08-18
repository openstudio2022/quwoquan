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

func (dispatch *readinessDispatch) GetSMSOTPDeliveryReadiness(
	context.Context,
) (accountapp.SMSOTPDeliveryReadiness, error) {
	if dispatch.err != nil {
		return accountapp.SMSOTPDeliveryReadiness{}, dispatch.err
	}
	return accountapp.SMSOTPDeliveryReadiness{Availability: "ready"}, nil
}

func TestOtpDeliveryReadinessOnlyReturnsBoundedBusinessState(t *testing.T) {
	ready := accountapp.NewAuthService(nil, nil, nil, nil, nil,
		accountapp.WithSMSOTPDeliveryReadinessQuery(&readinessDispatch{}),
	).GetOtpDeliveryReadiness(context.Background())
	if ready.Availability != "ready" || ready.RetryAfterSeconds != 0 {
		t.Fatalf("ready result = %+v", ready)
	}

	unavailable := accountapp.NewAuthService(nil, nil, nil, nil, nil,
		accountapp.WithSMSOTPDeliveryReadinessQuery(&readinessDispatch{
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
