package main

import (
	"context"
	"strings"
	"testing"
)

func TestConfiguredExternalAuthProviderModeDefaultsToRequired(t *testing.T) {
	t.Setenv("USER_AUTH_EXTERNAL_PROVIDER_MODE", "")
	mode, err := configuredExternalAuthProviderMode()
	if err != nil || mode != externalAuthProviderModeRequired {
		t.Fatalf("expected required default, mode=%q err=%v", mode, err)
	}
}

func TestConfiguredExternalAuthProviderModeRejectsUnknownValue(t *testing.T) {
	t.Setenv("USER_AUTH_EXTERNAL_PROVIDER_MODE", "optional")
	if _, err := configuredExternalAuthProviderMode(); err == nil {
		t.Fatal("unknown external auth mode must fail startup")
	}
}

func TestAnonymousOnlyModeDisablesExternalProvidersWithoutFakingIdentity(t *testing.T) {
	t.Setenv("USER_AUTH_EXTERNAL_PROVIDER_MODE", "anonymous_only")
	client, err := socialAuthProviderClient(config{})
	if err != nil {
		t.Fatalf("anonymous_only social client: %v", err)
	}
	if client.Supports("wechat") || client.Supports("alipay") || client.Supports("qq") {
		t.Fatal("anonymous_only must not claim an external provider is configured")
	}
	if _, err := client.Exchange(context.Background(), "wechat", "short-code", "ios", "1.0"); err == nil || !strings.Contains(err.Error(), "unavailable") {
		t.Fatalf("disabled provider must return unavailable, err=%v", err)
	}
	resolver, err := oneTapResolver(config{})
	if err != nil {
		t.Fatalf("anonymous_only one-tap resolver: %v", err)
	}
	if _, _, err := resolver.ResolvePhone(context.Background(), "cm", "carrier-token"); err == nil {
		t.Fatal("anonymous_only one-tap resolver must not fabricate a phone number")
	}
}
