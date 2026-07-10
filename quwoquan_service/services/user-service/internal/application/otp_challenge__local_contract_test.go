package application

import (
	"context"
	"fmt"
	"strings"
	"testing"
	"time"
)

type allowAllOtpRateLimiter struct{}

func (allowAllOtpRateLimiter) AllowSend(ctx context.Context, phone string) (bool, int, error) {
	_ = ctx
	_ = phone
	return true, 0, nil
}

func (allowAllOtpRateLimiter) SaveCode(ctx context.Context, phone, code string) error {
	_ = ctx
	_ = phone
	_ = code
	return nil
}

func (allowAllOtpRateLimiter) ReadCode(ctx context.Context, phone string) (string, bool, error) {
	_ = ctx
	_ = phone
	return "", false, nil
}

func (allowAllOtpRateLimiter) ClearCode(ctx context.Context, phone string) error {
	_ = ctx
	_ = phone
	return nil
}

type failingExternalClient struct{}

func (failingExternalClient) SubmitSMSOTP(ctx context.Context, req SMSOTPDispatchRequest) (ExternalInteractionAccepted, error) {
	_ = ctx
	_ = req
	return ExternalInteractionAccepted{}, fmt.Errorf("sms provider unavailable")
}

type acceptedExternalClient struct{}

func (acceptedExternalClient) SubmitSMSOTP(ctx context.Context, req SMSOTPDispatchRequest) (ExternalInteractionAccepted, error) {
	_ = ctx
	return ExternalInteractionAccepted{RequestID: req.RequestID, Status: "accepted"}, nil
}

func TestSendOtpPassThroughSkipsCodeCorrectnessOnlyWhenConfigured(t *testing.T) {
	store := NewMemoryOtpChallengeStore()
	svc := NewAuthService(
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
		WithOtpCodeStore(allowAllOtpRateLimiter{}),
		WithOtpChallengeStore(store),
		WithExternalInteractionClient(failingExternalClient{}),
		WithSmsOtpPassThroughConfig(SmsOtpPassThroughConfig{
			Mode:      SmsOtpPassThroughEnabled,
			DebtID:    "TECHDEBT-SMS-OTP-PASSTHROUGH-001",
			Owner:     "backend-team",
			ExpiresAt: time.Now().UTC().Add(24 * time.Hour),
		}),
	)
	result, err := svc.SendOtp(context.Background(), "+8618013813909", "ios-test", "ios", "1.0.0", "test")
	if err != nil {
		t.Fatalf("send otp: %v", err)
	}
	if result.DeliveryStatus != "pass_through" || result.DebugCode == "" {
		t.Fatalf("unexpected otp result: %#v", result)
	}
	challenge, err := store.FindLatestChallenge(context.Background(), "+8618013813909", time.Now().UTC())
	if err != nil {
		t.Fatalf("find challenge: %v", err)
	}
	if challenge == nil || challenge.Status != OtpChallengeStatusActive {
		t.Fatalf("challenge not active: %#v", challenge)
	}
	if err := svc.verifyOtp(context.Background(), "+8618013813909", "wrong-code"); err != nil {
		t.Fatalf("verify otp should skip code correctness under pass-through: %v", err)
	}
}

func TestSendOtpProviderFailureMapsStructuredError(t *testing.T) {
	store := NewMemoryOtpChallengeStore()
	svc := NewAuthService(
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
		WithOtpCodeStore(allowAllOtpRateLimiter{}),
		WithOtpChallengeStore(store),
		WithExternalInteractionClient(failingExternalClient{}),
	)

	_, err := svc.SendOtp(context.Background(), "+8618013813909", "ios-test", "ios", "1.0.0", "test")
	if err == nil {
		t.Fatal("expected provider failure")
	}
	if !strings.Contains(err.Error(), "USER.AUTH.otp_provider_failed") {
		t.Fatalf("expected otp_provider_failed, got %v", err)
	}
}

func TestOtpDebugRevealDoesNotSkipCodeCorrectness(t *testing.T) {
	store := NewMemoryOtpChallengeStore()
	svc := NewAuthService(
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
		WithOtpCodeStore(allowAllOtpRateLimiter{}),
		WithOtpChallengeStore(store),
		WithExternalInteractionClient(acceptedExternalClient{}),
		WithOtpDebugReveal(true),
	)
	result, err := svc.SendOtp(context.Background(), "+8618013813909", "ios-test", "ios", "1.0.0", "test")
	if err != nil {
		t.Fatalf("send otp: %v", err)
	}
	if result.DeliveryStatus != "queued" || result.DebugCode == "" {
		t.Fatalf("unexpected otp result: %#v", result)
	}
	if err := svc.verifyOtp(context.Background(), "+8618013813909", "wrong-code"); err == nil {
		t.Fatal("debug reveal must not bypass OTP code correctness")
	}
}
