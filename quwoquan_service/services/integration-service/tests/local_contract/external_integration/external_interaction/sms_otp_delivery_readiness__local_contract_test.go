// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-012
// readiness_case: get-sms-otp-delivery-readiness-local
package local_contract

import (
	"context"
	"errors"
	"testing"

	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
)

type readinessProbe struct {
	err   error
	calls int
}

func (probe *readinessProbe) CheckSMSOTPProviderReadiness(context.Context) error {
	probe.calls++
	return probe.err
}

type readinessRelay struct {
	err   error
	calls int
}

func (relay *readinessRelay) CheckSMSOTPResultRelayReadiness(context.Context) error {
	relay.calls++
	return relay.err
}

func TestSmsOtpDeliveryReadinessRequiresProviderProbeAndResultRelay(t *testing.T) {
	provider := &readinessProbe{}
	relay := &readinessRelay{}
	facade := application.NewSmsOtpDeliveryReadinessQueryFacade(provider, relay)
	ready := facade.GetSmsOtpDeliveryReadiness(context.Background())
	if ready.Availability != "ready" || ready.RetryAfterSeconds != 0 ||
		provider.calls != 1 || relay.calls != 1 {
		t.Fatalf("ready result=%+v providerCalls=%d relayCalls=%d", ready, provider.calls, relay.calls)
	}

	provider.err = errors.New("provider diagnostic must remain private")
	unavailable := facade.GetSmsOtpDeliveryReadiness(context.Background())
	if unavailable.Availability != "temporarily_unavailable" ||
		unavailable.RetryAfterSeconds != 5 || relay.calls != 1 {
		t.Fatalf("provider failure result=%+v relayCalls=%d", unavailable, relay.calls)
	}

	provider.err = nil
	relay.err = errors.New("callback relay diagnostic must remain private")
	unavailable = facade.GetSmsOtpDeliveryReadiness(context.Background())
	if unavailable.Availability != "temporarily_unavailable" ||
		unavailable.RetryAfterSeconds != 5 || relay.calls != 2 {
		t.Fatalf("relay failure result=%+v relayCalls=%d", unavailable, relay.calls)
	}
}

func TestSmsOtpDeliveryReadinessFailsClosedWithoutTypedPorts(t *testing.T) {
	result := application.NewSmsOtpDeliveryReadinessQueryFacade(nil, nil).
		GetSmsOtpDeliveryReadiness(context.Background())
	if result.Availability != "temporarily_unavailable" || result.RetryAfterSeconds != 5 {
		t.Fatalf("missing ports result=%+v", result)
	}
}
