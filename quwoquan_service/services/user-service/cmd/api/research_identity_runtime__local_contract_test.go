package main

import (
	"context"
	"encoding/base64"
	"strings"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
)

type researchRuntimeTransportProbe struct{}

func (*researchRuntimeTransportProbe) AppendDurable(
	context.Context,
	runtimemessaging.DurableMessage,
) (string, error) {
	return "1-0", nil
}

func (*researchRuntimeTransportProbe) SetDurableRetention(
	context.Context,
	string,
	time.Duration,
) error {
	return nil
}

func TestResearchIdentityRuntimeIsAlphaOnlyAndFailClosed(t *testing.T) {
	disabled := config{}
	if _, err := buildResearchSessionHandler("prod", disabled, nil); err != nil {
		t.Fatalf("disabled production composition should expose only unavailable authority: %v", err)
	}

	enabled := config{}
	enabled.ResearchIdentity.Enabled = true
	enabled.ResearchIdentity.TTLSeconds = 300
	if _, err := buildResearchSessionHandler("prod", enabled, &researchRuntimeTransportProbe{}); err == nil ||
		!strings.Contains(err.Error(), "only be enabled in nonproduction") {
		t.Fatalf("production must reject enabled research identity authority: %v", err)
	}

	t.Setenv(researchIdentityKeyEnv, "")
	t.Setenv(researchIdentityAllowlistEnv, "")
	if _, err := buildResearchSessionHandler("alpha", enabled, &researchRuntimeTransportProbe{}); err == nil {
		t.Fatal("alpha must fail startup without the real secret authority")
	}

	t.Setenv(
		researchIdentityKeyEnv,
		base64.StdEncoding.EncodeToString([]byte("alpha-research-attestation-key-32-bytes")),
	)
	const accountID = "uo_01_ph_333a_01j00000000000000000000000"
	const phone = "+8619910000000"
	t.Setenv(researchIdentityAllowlistEnv, `["`+accountID+`"]`)
	t.Setenv(
		managedAcceptanceIdentityEnv,
		`{"phone":"`+phone+`","accountId":"`+accountID+`","subjectHash":"sha256:db305c2da7a9e9777bb3a9606e404ed99ab276aeb2574b92854af7c6ede62c6b"}`,
	)
	if _, err := buildResearchSessionHandler("alpha", enabled, &researchRuntimeTransportProbe{}); err != nil {
		t.Fatalf("valid alpha authority composition failed: %v", err)
	}
}

func TestManagedAcceptanceIdentityRequiresOneCompleteRuntimeBinding(t *testing.T) {
	t.Setenv(managedAcceptanceIdentityEnv, "")
	if _, err := loadManagedAcceptanceIdentity(); err == nil {
		t.Fatal("missing managed acceptance identity must fail closed")
	}
	t.Setenv(managedAcceptanceIdentityEnv, `{"phone":"+8619910000000","accountId":"uo_01_ph_333a_01j00000000000000000000000","subjectHash":"sha256:db305c2da7a9e9777bb3a9606e404ed99ab276aeb2574b92854af7c6ede62c6b"}`)
	identity, err := loadManagedAcceptanceIdentity()
	if err != nil {
		t.Fatalf("valid managed acceptance identity failed: %v", err)
	}
	if identity.Phone != "+8619910000000" ||
		identity.AccountID != "uo_01_ph_333a_01j00000000000000000000000" {
		t.Fatalf("managed acceptance identity drifted: %+v", identity)
	}
}
