package application

import (
	"context"
	"encoding/base64"
	"fmt"
	"strings"
	"testing"

	"quwoquan_service/runtime/otpseal"
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

func testOTPCodeSealer(t *testing.T) *otpseal.Sealer {
	t.Helper()
	sealer, err := otpseal.NewFromBase64("test-k1", map[string]string{
		"test-k1": base64.StdEncoding.EncodeToString([]byte("0123456789abcdef0123456789abcdef")),
	})
	if err != nil {
		t.Fatal(err)
	}
	return sealer
}

func (acceptedExternalClient) SubmitSMSOTP(ctx context.Context, req SMSOTPDispatchRequest) (ExternalInteractionAccepted, error) {
	_ = ctx
	return ExternalInteractionAccepted{RequestID: req.RequestID, Status: "accepted"}, nil
}

func TestSendOtpProviderFailureMapsStructuredError(t *testing.T) {
	store := NewMemoryOtpChallengeStore()
	svc := NewAuthService(
		nil,
		nil,
		nil,
		nil,
		nil,
		WithOtpCodeStore(allowAllOtpRateLimiter{}),
		WithOtpChallengeStore(store),
		WithOTPCodeSealer(testOTPCodeSealer(t)),
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

func TestSendOtpNeverRevealsOrBypassesCodeCorrectness(t *testing.T) {
	store := NewMemoryOtpChallengeStore()
	svc := NewAuthService(
		nil,
		nil,
		nil,
		nil,
		nil,
		WithOtpCodeStore(allowAllOtpRateLimiter{}),
		WithOtpChallengeStore(store),
		WithOTPCodeSealer(testOTPCodeSealer(t)),
		WithExternalInteractionClient(acceptedExternalClient{}),
	)
	result, err := svc.SendOtp(context.Background(), "+8618013813909", "ios-test", "ios", "1.0.0", "test")
	if err != nil {
		t.Fatalf("send otp: %v", err)
	}
	if result.DeliveryStatus != "queued" {
		t.Fatalf("unexpected otp result: %#v", result)
	}
	if err := svc.verifyOtp(context.Background(), "+8618013813909", "wrong-code"); err == nil {
		t.Fatal("debug reveal must not bypass OTP code correctness")
	}
}

func TestFixedNonProductionOTPUsesChallengeExpiryAndOneTimeConsumption(t *testing.T) {
	store := NewMemoryOtpChallengeStore()
	svc := NewAuthService(
		nil,
		nil,
		nil,
		nil,
		nil,
		WithOtpCodeStore(allowAllOtpRateLimiter{}),
		WithOtpChallengeStore(store),
		WithOTPCodeSealer(testOTPCodeSealer(t)),
		WithOTPCodeGenerator(func() (string, error) { return "123456", nil }),
		WithExternalInteractionClient(acceptedExternalClient{}),
	)
	if _, err := svc.SendOtp(context.Background(), "+8618013813909", "ios-test", "ios", "1.0.0", "test"); err != nil {
		t.Fatalf("send fixed OTP: %v", err)
	}
	if err := svc.verifyOtp(context.Background(), "+8618013813909", "654321"); err == nil ||
		!strings.Contains(err.Error(), "USER.AUTH.otp_mismatch") {
		t.Fatalf("wrong fixed OTP must be rejected, got %v", err)
	}
	if err := svc.verifyOtp(context.Background(), "+8618013813909", "123456"); err != nil {
		t.Fatalf("fixed OTP must verify once: %v", err)
	}
	if err := svc.verifyOtp(context.Background(), "+8618013813909", "123456"); err == nil ||
		!strings.Contains(err.Error(), "USER.AUTH.otp_expired") {
		t.Fatalf("consumed fixed OTP must not be reusable, got %v", err)
	}
}

func TestFixedNonProductionOTPLocksChallengeAfterFiveMismatches(t *testing.T) {
	store := NewMemoryOtpChallengeStore()
	svc := NewAuthService(
		nil,
		nil,
		nil,
		nil,
		nil,
		WithOtpCodeStore(allowAllOtpRateLimiter{}),
		WithOtpChallengeStore(store),
		WithOTPCodeSealer(testOTPCodeSealer(t)),
		WithOTPCodeGenerator(func() (string, error) { return "123456", nil }),
		WithExternalInteractionClient(acceptedExternalClient{}),
	)
	if _, err := svc.SendOtp(context.Background(), "+8618013813909", "ios-test", "ios", "1.0.0", "test"); err != nil {
		t.Fatalf("send fixed OTP: %v", err)
	}
	for attempt := 1; attempt <= maxOTPFailCount; attempt++ {
		err := svc.verifyOtp(context.Background(), "+8618013813909", "654321")
		if attempt < maxOTPFailCount && (err == nil || !strings.Contains(err.Error(), "USER.AUTH.otp_mismatch")) {
			t.Fatalf("attempt %d must return mismatch, got %v", attempt, err)
		}
		if attempt == maxOTPFailCount && (err == nil || !strings.Contains(err.Error(), "USER.AUTH.otp_attempts_exceeded")) {
			t.Fatalf("attempt %d must lock challenge, got %v", attempt, err)
		}
	}
	if err := svc.verifyOtp(context.Background(), "+8618013813909", "123456"); err == nil ||
		!strings.Contains(err.Error(), "USER.AUTH.otp_expired") {
		t.Fatalf("locked challenge must reject the correct code, got %v", err)
	}
}
