// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
package local_contract

import (
	"encoding/base64"
	"strings"
	"testing"

	sessionapp "quwoquan_service/services/user-service/internal/account/account_session/application"
)

const (
	managedAcceptanceAccountID = "uo_01_ph_333a_01j00000000000000000000000"
	managedAcceptancePhone     = "+8619910000000"
	managedAcceptanceJSON      = `{"phone":"` + managedAcceptancePhone +
		`","accountId":"` + managedAcceptanceAccountID +
		`","subjectHash":"sha256:db305c2da7a9e9777bb3a9606e404ed99ab276aeb2574b92854af7c6ede62c6b"}`
)

func TestResearchIdentityAuthorityIsAlphaOnlyAndFailClosed(t *testing.T) {
	disabled, err := sessionapp.ResolveResearchIdentityAuthority("prod", false, 0)
	if err != nil {
		t.Fatalf("disabled production composition should resolve an unavailable authority: %v", err)
	}
	if disabled.Enabled {
		t.Fatal("disabled composition must not enable the research identity authority")
	}

	if _, err := sessionapp.ResolveResearchIdentityAuthority("prod", true, 300); err == nil ||
		!strings.Contains(err.Error(), "only be enabled in nonproduction") {
		t.Fatalf("production must reject enabled research identity authority: %v", err)
	}

	t.Setenv(sessionapp.ResearchIdentityKeyEnv, "")
	t.Setenv(sessionapp.ResearchIdentityAllowlistEnv, "")
	if _, err := sessionapp.ResolveResearchIdentityAuthority("alpha", true, 300); err == nil {
		t.Fatal("alpha must fail startup without the real secret authority")
	}

	t.Setenv(
		sessionapp.ResearchIdentityKeyEnv,
		base64.StdEncoding.EncodeToString([]byte("alpha-research-attestation-key-32-bytes")),
	)
	t.Setenv(sessionapp.ResearchIdentityAllowlistEnv, `["`+managedAcceptanceAccountID+`"]`)
	t.Setenv(sessionapp.ManagedAcceptanceIdentityEnv, managedAcceptanceJSON)
	authority, err := sessionapp.ResolveResearchIdentityAuthority("alpha", true, 300)
	if err != nil {
		t.Fatalf("valid alpha authority composition failed: %v", err)
	}
	if !authority.Enabled || len(authority.AccountIDs) != 1 ||
		authority.AccountIDs[0] != managedAcceptanceAccountID {
		t.Fatalf("alpha authority must bind exactly the managed acceptance account: %+v", authority)
	}
}

func TestResearchIdentityAuthorityRejectsAllowlistDrift(t *testing.T) {
	t.Setenv(
		sessionapp.ResearchIdentityKeyEnv,
		base64.StdEncoding.EncodeToString([]byte("alpha-research-attestation-key-32-bytes")),
	)
	t.Setenv(sessionapp.ManagedAcceptanceIdentityEnv, managedAcceptanceJSON)
	t.Setenv(
		sessionapp.ResearchIdentityAllowlistEnv,
		`["uo_01_ph_333a_01j99999999999999999999999"]`,
	)
	if _, err := sessionapp.ResolveResearchIdentityAuthority("alpha", true, 300); err == nil {
		t.Fatal("allowlist drifting from the managed acceptance identity must fail closed")
	}
}

func TestManagedAcceptanceIdentityRequiresOneCompleteRuntimeBinding(t *testing.T) {
	t.Setenv(sessionapp.ManagedAcceptanceIdentityEnv, "")
	if _, err := sessionapp.LoadManagedAcceptanceIdentity(); err == nil {
		t.Fatal("missing managed acceptance identity must fail closed")
	}
	t.Setenv(sessionapp.ManagedAcceptanceIdentityEnv, managedAcceptanceJSON)
	identity, err := sessionapp.LoadManagedAcceptanceIdentity()
	if err != nil {
		t.Fatalf("valid managed acceptance identity failed: %v", err)
	}
	if identity.Phone != managedAcceptancePhone ||
		identity.AccountID != managedAcceptanceAccountID {
		t.Fatalf("managed acceptance identity drifted: %+v", identity)
	}
}
