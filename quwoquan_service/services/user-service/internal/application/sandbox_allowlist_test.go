package application

import (
	"context"
	"testing"
	"time"
)

func futureExpiry() time.Time { return time.Now().UTC().Add(24 * time.Hour) }

func TestSandboxAllowlistPhoneAndTokenMatching(t *testing.T) {
	now := time.Now().UTC()
	list := SandboxAllowlist{
		Enabled:   true,
		Phones:    []string{"+8617000000000", "+86188"},
		Tokens:    []string{"sandbox-wechat-"},
		DebtID:    "TECHDEBT-LOGIN-SANDBOX-ALLOWLIST-GAMMA-001",
		Owner:     "backend-team",
		ExpiresAt: futureExpiry(),
	}
	if !list.AllowsPhone("+8617000000000", now) {
		t.Fatal("exact phone should match")
	}
	if !list.AllowsPhone("+8618812345678", now) {
		t.Fatal("prefix 号段 should match")
	}
	if list.AllowsPhone("+8613900000000", now) {
		t.Fatal("non-allowlisted phone must not match")
	}
	if !list.AllowsToken("sandbox-wechat-abc", now) {
		t.Fatal("token prefix should match")
	}
	if list.AllowsToken("real-wechat-code", now) {
		t.Fatal("non-allowlisted token must not match")
	}
}

func TestSandboxAllowlistDisabledOrExpired(t *testing.T) {
	now := time.Now().UTC()
	disabled := SandboxAllowlist{Enabled: false, Phones: []string{"+8617000000000"}}
	if disabled.AllowsPhone("+8617000000000", now) {
		t.Fatal("disabled allowlist must never match")
	}
	expired := SandboxAllowlist{
		Enabled:   true,
		Phones:    []string{"+8617000000000"},
		ExpiresAt: now.Add(-time.Hour),
	}
	if expired.AllowsPhone("+8617000000000", now) {
		t.Fatal("expired allowlist must not match")
	}
}

func TestSandboxAllowlistValidate(t *testing.T) {
	// production must reject any configured allowlist
	prod := SandboxAllowlist{Enabled: true, Phones: []string{"+8617000000000"}, DebtID: "x", Owner: "y", ExpiresAt: futureExpiry()}
	if err := prod.Validate(true); err == nil {
		t.Fatal("production must reject sandbox allowlist")
	}
	if err := (SandboxAllowlist{}).Validate(true); err != nil {
		t.Fatalf("empty allowlist must pass production validate: %v", err)
	}
	// non-production enabled requires debt/owner/expires + entries
	missing := SandboxAllowlist{Enabled: true, Phones: []string{"+8617000000000"}}
	if err := missing.Validate(false); err == nil {
		t.Fatal("enabled allowlist requires debt/owner/expires")
	}
	empty := SandboxAllowlist{Enabled: true, DebtID: "x", Owner: "y", ExpiresAt: futureExpiry()}
	if err := empty.Validate(false); err == nil {
		t.Fatal("enabled allowlist requires non-empty phones/tokens")
	}
	ok := SandboxAllowlist{Enabled: true, Phones: []string{"+8617000000000"}, DebtID: "x", Owner: "y", ExpiresAt: futureExpiry()}
	if err := ok.Validate(false); err != nil {
		t.Fatalf("well-formed allowlist must pass: %v", err)
	}
}

// gamma 受控放通：命中 allowlist 的号码回填验证码并标记 sandbox；非白名单号码走真实下发严格校验。
func TestSendOtpSandboxAllowlistRevealsForAllowlistedPhoneOnly(t *testing.T) {
	store := NewMemoryOtpChallengeStore()
	svc := NewAuthService(
		nil, nil, nil, nil, nil, nil,
		WithOtpCodeStore(allowAllOtpRateLimiter{}),
		WithOtpChallengeStore(store),
		WithExternalInteractionClient(acceptedExternalClient{}),
		WithSmsOtpSandboxAllowlist(SandboxAllowlist{
			Enabled:   true,
			Phones:    []string{"+8617000000000"},
			DebtID:    "TECHDEBT-LOGIN-SANDBOX-ALLOWLIST-GAMMA-001",
			Owner:     "backend-team",
			ExpiresAt: futureExpiry(),
		}),
	)

	allowed, err := svc.SendOtp(context.Background(), "+8617000000000", "ios-test", "ios", "1.0.0", "test")
	if err != nil {
		t.Fatalf("send otp allowlisted: %v", err)
	}
	if allowed.DeliveryStatus != "sandbox" || allowed.DebugCode == "" {
		t.Fatalf("allowlisted phone must get sandbox controlled pass-through: %#v", allowed)
	}
	// debug code is the real code → must still pass strict verification
	if err := svc.verifyOtp(context.Background(), "+8617000000000", allowed.DebugCode); err != nil {
		t.Fatalf("sandbox debug code must verify: %v", err)
	}

	other, err := svc.SendOtp(context.Background(), "+8613900000000", "ios-test", "ios", "1.0.0", "test")
	if err != nil {
		t.Fatalf("send otp non-allowlisted: %v", err)
	}
	if other.DeliveryStatus == "sandbox" || other.DebugCode != "" {
		t.Fatalf("non-allowlisted phone must not get sandbox reveal: %#v", other)
	}
}
