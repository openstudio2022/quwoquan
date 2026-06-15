package integration

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/services/user-service/internal/application"
)

func TestMockExternalAuthProviderDeterministicAndSupported(t *testing.T) {
	client := NewMockExternalAuthProviderClient()
	for _, p := range []string{application.SocialProviderWechat, application.SocialProviderAlipay, application.SocialProviderQq} {
		if !client.Supports(p) {
			t.Fatalf("mock must support %s", p)
		}
		first, err := client.Exchange(context.Background(), p, "code-123", "ios", "1.0.0")
		if err != nil {
			t.Fatalf("exchange %s: %v", p, err)
		}
		if first.OpenID == "" || first.DisplayName == "" || first.AvatarURL == "" {
			t.Fatalf("%s identity must be populated: %#v", p, first)
		}
		second, _ := client.Exchange(context.Background(), p, "code-123", "ios", "1.0.0")
		if first.StableKey() != second.StableKey() {
			t.Fatalf("%s identity must be deterministic for same authCode", p)
		}
		other, _ := client.Exchange(context.Background(), p, "code-456", "ios", "1.0.0")
		if first.StableKey() == other.StableKey() {
			t.Fatalf("%s different authCode must yield different identity", p)
		}
	}
}

func TestMockExternalAuthProviderCancellation(t *testing.T) {
	client := NewMockExternalAuthProviderClient()
	if _, err := client.Exchange(context.Background(), "wechat", "user-cancelled-code", "ios", "1.0.0"); err == nil {
		t.Fatal("cancellation authCode must produce error")
	}
}

type recordingProvider struct{ called bool }

func (r *recordingProvider) Supports(string) bool { return true }
func (r *recordingProvider) Exchange(_ context.Context, provider, authCode, _, _ string) (application.ExternalIdentity, error) {
	r.called = true
	return application.ExternalIdentity{Provider: provider, OpenID: "real_" + authCode}, nil
}

func TestSandboxExternalAuthProviderControlledPassThrough(t *testing.T) {
	allow := application.SandboxAllowlist{
		Enabled:   true,
		Tokens:    []string{"sandbox-wechat-"},
		DebtID:    "TECHDEBT-LOGIN-SANDBOX-ALLOWLIST-GAMMA-001",
		Owner:     "backend-team",
		ExpiresAt: time.Now().UTC().Add(24 * time.Hour),
	}
	fallback := &recordingProvider{}
	client := NewSandboxExternalAuthProviderClient(allow, fallback)

	sandboxIdentity, err := client.Exchange(context.Background(), "wechat", "sandbox-wechat-001", "ios", "1.0.0")
	if err != nil {
		t.Fatalf("sandbox exchange: %v", err)
	}
	if fallback.called {
		t.Fatal("allowlisted token must not hit real provider")
	}
	if sandboxIdentity.OpenID == "" {
		t.Fatalf("sandbox identity must be populated: %#v", sandboxIdentity)
	}

	if _, err := client.Exchange(context.Background(), "wechat", "real-user-code", "ios", "1.0.0"); err != nil {
		t.Fatalf("non-allowlisted should delegate to fallback: %v", err)
	}
	if !fallback.called {
		t.Fatal("non-allowlisted token must delegate to real provider")
	}
}

func TestHTTPExternalAuthProviderUnavailableWhenUnconfigured(t *testing.T) {
	client := NewHTTPExternalAuthProviderClient(map[string]ProviderOAuthConfig{}, nil)
	if client.Supports("wechat") {
		t.Fatal("unconfigured provider must not report supported")
	}
	if _, err := client.Exchange(context.Background(), "alipay", "code", "ios", "1.0.0"); err == nil {
		t.Fatal("unconfigured provider must return structured unavailable, not fake success")
	}
}
