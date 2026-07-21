package main

import (
	"errors"
	"testing"
)

func TestCarrierPhoneResolverFailsClosedWithoutCredentials(t *testing.T) {
	t.Setenv("ALIYUN_DYPNS_ACCESS_KEY_ID", "")
	t.Setenv("ALIYUN_DYPNS_ACCESS_KEY_SECRET", "")

	if _, err := newCarrierPhoneResolver(); err == nil {
		t.Fatal("missing carrier credentials must fail composition")
	}
}

func TestFederatedLoginBindingsFailClosedWithoutCredentials(t *testing.T) {
	t.Setenv("WECHAT_OAUTH_APP_ID", "")

	if _, err := newFederatedLoginBindings(nil); err == nil {
		t.Fatal("missing federated credentials must fail composition")
	}
}

func TestReleaseAuthenticationBindingsExposeBlockedCapabilityForDegradation(t *testing.T) {
	t.Setenv("APP_ENV", "beta")
	t.Setenv("ALIYUN_DYPNS_ACCESS_KEY_ID", "carrier-key")
	t.Setenv("ALIYUN_DYPNS_ACCESS_KEY_SECRET", "carrier-secret")
	t.Setenv("WECHAT_OAUTH_APP_ID", "wechat-app")

	if _, err := newCarrierPhoneResolver(); !errors.Is(
		err,
		ErrAuthRuntimeCapabilityBlocked,
	) {
		t.Fatalf("blocked one-tap descriptor error = %v", err)
	}
	if _, err := newFederatedLoginBindings(nil); !errors.Is(
		err,
		ErrAuthRuntimeCapabilityBlocked,
	) {
		t.Fatalf("blocked social-login descriptor error = %v", err)
	}
}
