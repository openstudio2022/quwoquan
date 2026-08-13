// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-001
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#req-008
package application_test

import (
	"strings"
	"testing"

	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	app "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
)

// 发布义务（policyDecisionRef/policyDigest/obligationDigest）是治理证据，
// 属于 owner 侧：端只声明 riskControlPolicyRef，服务对实际 policy 内容
// 确定性派生义务；显式提供的运营管控值不被覆盖；缺 riskControlPolicyRef
// 时不派生，让 publish 按既有校验 fail-closed。

func obligationPolicyFixture() contract.GatheringPolicySet {
	return contract.GatheringPolicySet{
		AudiencePolicy:  contract.GatheringAudiencePolicyPublic,
		AdmissionPolicy: contract.GatheringAdmissionPolicyApproval,
		CapacityPolicy: contract.GatheringCapacityPolicy{
			MaxParticipants: 4,
		},
		DisclosurePolicy: contract.GatheringDisclosurePolicy{
			TimeDisclosure:   contract.GatheringTimeDisclosureExact,
			PlaceDisclosure:  contract.GatheringPlaceDisclosureAfterJoin,
			RosterDisclosure: contract.GatheringRosterDisclosureCountOnly,
		},
		RiskControlPolicyRef: "risk/standard-day-public-v1",
	}
}

func TestResolveStandardPublishObligationsDerivesDeterministicEvidence(t *testing.T) {
	first := app.ResolveStandardPublishObligations(obligationPolicyFixture())
	second := app.ResolveStandardPublishObligations(obligationPolicyFixture())

	if first.PolicyDecisionRef != "risk/standard-day-public-v1:standard" {
		t.Fatalf("unexpected decision ref: %q", first.PolicyDecisionRef)
	}
	if !strings.HasPrefix(first.PolicyDigest, "sha256:") ||
		!strings.HasPrefix(first.ObligationDigest, "sha256:") {
		t.Fatalf(
			"digests must be sha256 refs: %q / %q",
			first.PolicyDigest,
			first.ObligationDigest,
		)
	}
	if first.PolicyDigest != second.PolicyDigest ||
		first.ObligationDigest != second.ObligationDigest {
		t.Fatalf("obligation derivation must be deterministic")
	}
}

func TestResolveStandardPublishObligationsTracksPolicyContent(t *testing.T) {
	base := app.ResolveStandardPublishObligations(obligationPolicyFixture())
	changed := obligationPolicyFixture()
	changed.CapacityPolicy.MaxParticipants = 8
	other := app.ResolveStandardPublishObligations(changed)

	if base.PolicyDigest == other.PolicyDigest {
		t.Fatalf("policy digest must change when policy content changes")
	}
}

func TestResolveStandardPublishObligationsKeepsExplicitGovernanceValues(t *testing.T) {
	policy := obligationPolicyFixture()
	policy.PolicyDecisionRef = "decision/ops-hold"
	resolved := app.ResolveStandardPublishObligations(policy)

	if resolved.PolicyDecisionRef != "decision/ops-hold" {
		t.Fatalf("explicit decision ref must not be overwritten")
	}
	if resolved.PolicyDigest != "" || resolved.ObligationDigest != "" {
		t.Fatalf("partially provided governance evidence must stay untouched")
	}
}

func TestResolveStandardPublishObligationsRequiresRiskPolicyRef(t *testing.T) {
	policy := obligationPolicyFixture()
	policy.RiskControlPolicyRef = "  "
	resolved := app.ResolveStandardPublishObligations(policy)

	if resolved.PolicyDecisionRef != "" ||
		resolved.PolicyDigest != "" ||
		resolved.ObligationDigest != "" {
		t.Fatalf("missing risk policy ref must stay fail-closed")
	}
}
