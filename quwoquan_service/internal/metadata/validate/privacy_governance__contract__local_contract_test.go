package validate

import (
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
func TestCanonicalPrivacyGovernanceConsumesEveryTypedPolicy(t *testing.T) {
	t.Parallel()

	if issues := validatePrivacyGovernance(canonicalPrivacyGraph()); len(issues) != 0 {
		t.Fatalf("canonical privacy rejected: %+v", issues)
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
func TestPrivacyAppLogPolicyFailsClosedAgainstFieldBaseline(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		mutate func(*graph.ContractGraph)
		codes  []string
	}{
		"classification downgrade": {
			mutate: func(contractGraph *graph.ContractGraph) {
				privacyPolicy(contractGraph).Classification = ast.PrivacyClassificationPublic
			},
			codes: []string{"CONTRACT.PRIVACY.CLASSIFICATION_DOWNGRADE"},
		},
		"unknown classification": {
			mutate: func(contractGraph *graph.ContractGraph) {
				privacyPolicy(contractGraph).Classification = "PERSONAL"
			},
			codes: []string{"CONTRACT.PRIVACY.INVALID_CLASSIFICATION"},
		},
		"field log policy widened": {
			mutate: func(contractGraph *graph.ContractGraph) {
				contractGraph.Governance.Fields[0].LogPolicy = "drop"
			},
			codes: []string{"CONTRACT.PRIVACY.LOG_POLICY_WIDENED"},
		},
		"PII allowed raw": {
			mutate: func(contractGraph *graph.ContractGraph) {
				contractGraph.Governance.Fields[0].LogPolicy = "allow"
				policy := privacyPolicy(contractGraph)
				policy.AppLog = ast.PrivacyAppLogAllow
				policy.MaskStrategy = ""
			},
			codes: []string{"CONTRACT.PRIVACY.UNSAFE_APP_LOG_ACTION"},
		},
		"mask without strategy": {
			mutate: func(contractGraph *graph.ContractGraph) {
				privacyPolicy(contractGraph).MaskStrategy = ""
			},
			codes: []string{"CONTRACT.PRIVACY.INVALID_APP_LOG_PARAMETERS"},
		},
	}
	for name, test := range tests {
		name := name
		test := test
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			contractGraph := canonicalPrivacyGraph()
			test.mutate(contractGraph)
			assertGovernanceIssueCodes(t, validatePrivacyGovernance(contractGraph), test.codes...)
		})
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
func TestPrivacyVisibilityDeletionAndAnonymizationFailClosed(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		mutate func(*graph.ContractGraph)
		codes  []string
	}{
		"identity mismatch": {
			mutate: func(contractGraph *graph.ContractGraph) {
				privacyDefinition(contractGraph).ObjectID = "content.comment"
			},
			codes: []string{"CONTRACT.PRIVACY.IDENTITY_MISMATCH"},
		},
		"visibility wildcard combined": {
			mutate: func(contractGraph *graph.ContractGraph) {
				privacyDefinition(contractGraph).Document.FieldVisibility[0].Visibility = []string{"all", "app"}
			},
			codes: []string{"CONTRACT.PRIVACY.INVALID_VISIBILITY_SET"},
		},
		"unknown visibility": {
			mutate: func(contractGraph *graph.ContractGraph) {
				privacyDefinition(contractGraph).Document.FieldVisibility[0].Visibility = []string{"partner"}
			},
			codes: []string{"CONTRACT.PRIVACY.UNKNOWN_VISIBILITY"},
		},
		"deletion disabled while work declared": {
			mutate: func(contractGraph *graph.ContractGraph) {
				value := false
				privacyDefinition(contractGraph).Document.DataLifecycle.DeletionOnUserRequest = &value
			},
			codes: []string{"CONTRACT.PRIVACY.INACTIVE_DELETION_POLICY"},
		},
		"unknown canonical target": {
			mutate: func(contractGraph *graph.ContractGraph) {
				privacyDefinition(contractGraph).Document.DataLifecycle.DeletionCascade[0].ObjectID = "content.missing"
			},
			codes: []string{"CONTRACT.PRIVACY.UNKNOWN_DELETION_TARGET"},
		},
		"duplicate canonical target": {
			mutate: func(contractGraph *graph.ContractGraph) {
				lifecycle := privacyDefinition(contractGraph).Document.DataLifecycle
				lifecycle.DeletionCascade = append(lifecycle.DeletionCascade, lifecycle.DeletionCascade[0])
			},
			codes: []string{"CONTRACT.PRIVACY.DUPLICATE_DELETION_TARGET"},
		},
		"invalid CDN purge strategy": {
			mutate: func(contractGraph *graph.ContractGraph) {
				privacyDefinition(contractGraph).Document.DataLifecycle.DeletionCascade[0].CDNPurgeDelayHours = nil
			},
			codes: []string{"CONTRACT.PRIVACY.INVALID_DELETION_STRATEGY"},
		},
		"invalid anonymization": {
			mutate: func(contractGraph *graph.ContractGraph) {
				privacyDefinition(contractGraph).Document.DataLifecycle.AnonymizationOnDelete[0].Placeholder = ""
			},
			codes: []string{"CONTRACT.PRIVACY.INVALID_ANONYMIZATION_STRATEGY"},
		},
	}
	for name, test := range tests {
		name := name
		test := test
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			contractGraph := canonicalPrivacyGraph()
			test.mutate(contractGraph)
			assertGovernanceIssueCodes(t, validatePrivacyGovernance(contractGraph), test.codes...)
		})
	}
}

func canonicalPrivacyGraph() *graph.ContractGraph {
	retentionDays := 30
	deletionOnRequest := true
	softDeleteFirst := true
	purgeDelay := 24
	return &graph.ContractGraph{
		Objects: []ast.Object{
			{ID: "content.post", Domain: "content", Name: "Post"},
			{ID: "content.media_asset", Domain: "content", Name: "MediaAsset"},
		},
		Governance: ast.MetadataGovernance{
			Fields: []ast.FieldDefinition{
				{
					ObjectID: "content.post", Entity: "Post", Name: "location",
					Classification: "PII", LogPolicy: "mask",
				},
				{
					ObjectID: "content.post", Entity: "Post", Name: "authorId",
					Classification: "PUBLIC", LogPolicy: "allow",
				},
			},
			Objects: []ast.ObjectGovernance{{
				ObjectID: "content.post",
				Privacy: &ast.PrivacyDefinition{
					ObjectID: "content.post",
					Document: ast.PrivacyDocument{
						Description: "fixture privacy",
						AppLogPolicy: []ast.PrivacyAppLogPolicy{{
							Field: "location", Classification: ast.PrivacyClassificationPII,
							AppLog: ast.PrivacyAppLogMask, MaskStrategy: "city_level_only",
						}},
						FieldVisibility: []ast.PrivacyFieldVisibility{{
							Field: "authorId", Visibility: []string{"all"},
						}},
						DataLifecycle: &ast.PrivacyDataLifecycle{
							RetentionDays:         &retentionDays,
							DeletionOnUserRequest: &deletionOnRequest,
							DeletionCascade: []ast.PrivacyDeletionCascade{{
								ObjectID:        "content.media_asset",
								Strategy:        ast.PrivacyDeletionSoftDeleteThenCDNPurge,
								SoftDeleteFirst: &softDeleteFirst, CDNPurgeDelayHours: &purgeDelay,
							}},
							AnonymizationOnDelete: []ast.PrivacyAnonymization{{
								Field: "authorId", Strategy: ast.PrivacyAnonymizationReplaceWithPlaceholder,
								Placeholder: "[deleted_user]",
							}},
						},
					},
					SourcePath: "content/content/post/privacy.yaml",
				},
			}},
		},
	}
}

func privacyDefinition(contractGraph *graph.ContractGraph) *ast.PrivacyDefinition {
	return contractGraph.Governance.Objects[0].Privacy
}

func privacyPolicy(contractGraph *graph.ContractGraph) *ast.PrivacyAppLogPolicy {
	return &privacyDefinition(contractGraph).Document.AppLogPolicy[0]
}
