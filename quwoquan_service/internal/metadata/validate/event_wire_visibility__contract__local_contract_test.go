package validate

import (
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

// spec_ref: specs/feature-tree/runtime/runtime-governance/spec.md#sit-003
func TestEventGovernanceRequiresOneUniqueOutboxWireIdentity(t *testing.T) {
	t.Parallel()

	contractGraph := &graph.ContractGraph{Governance: ast.MetadataGovernance{
		Objects: []ast.ObjectGovernance{
			{ObjectID: "content.post", Events: []ast.EventDefinition{{
				ObjectID: "content.post", Name: "PostPublished",
				DeliverySemantics: "transactional_outbox",
				SourcePath:        "content/post/events.yaml",
			}}},
			{ObjectID: "content.comment", Events: []ast.EventDefinition{{
				ObjectID: "content.comment", Name: "CommentCreated",
				DeliverySemantics: "transactional_outbox",
				WireEventType:     "shared.event.type",
				SourcePath:        "content/comment/events.yaml",
			}, {
				ObjectID: "content.comment", Name: "CommentDeleted",
				DeliverySemantics: "transactional_outbox",
				WireEventType:     "shared.event.type",
				SourcePath:        "content/comment/events.yaml",
			}}},
		},
	}}

	issues := validateEventGovernance(contractGraph)
	assertEventGovernanceIssueCount(
		t,
		issues,
		"CONTRACT.EVENT.MISSING_WIRE_EVENT_TYPE",
		1,
	)
	assertEventGovernanceIssueCount(
		t,
		issues,
		"CONTRACT.EVENT.DUPLICATE_WIRE_EVENT_TYPE",
		1,
	)
}

func TestEventPayloadVisibilityIsAudienceOnlyAndFailClosedAcrossServices(t *testing.T) {
	t.Parallel()

	for name, tc := range map[string]struct {
		consumerDomain string
		visibility     []string
		wantMismatch   int
	}{
		"same service internal": {
			consumerDomain: "content",
			visibility:     []string{"content-service-internal"},
		},
		"other service rejected": {
			consumerDomain: "recommendation",
			visibility:     []string{"content-service-internal"},
			wantMismatch:   1,
		},
		"first party service audience accepted": {
			consumerDomain: "recommendation",
			visibility:     []string{"first_party_service_internal"},
		},
	} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			producer := ast.Object{
				ID: "content.post", Domain: "content", Name: "Post",
				SourcePath: "content/post/object.yaml",
			}
			consumer := ast.Object{
				ID: tc.consumerDomain + ".candidate_view", Domain: tc.consumerDomain,
				Name: "CandidateView", Kind: ast.ObjectKindProjection,
				SourcePath: tc.consumerDomain + "/candidate_view/object.yaml",
				Lifecycle: &ast.LifecycleDefinition{
					SourceEvents: []string{"content.post.PostPublished"},
					EventConsumers: []ast.LifecycleEventConsumer{{
						Name: "post-projector", Kind: "projector",
						Facet: "CandidateProjector", Method: "Project",
						Idempotency: "aggregate_version",
					}},
				},
			}
			contractGraph := &graph.ContractGraph{
				Objects: []ast.Object{producer, consumer},
				Governance: ast.MetadataGovernance{Objects: []ast.ObjectGovernance{{
					ObjectID: producer.ID,
					Events: []ast.EventDefinition{{
						ObjectID: producer.ID, Name: "PostPublished",
						DeliverySemantics: "transactional_outbox",
						WireEventType:     "PostPublished",
						PayloadEntity:     "Post",
						PayloadFields:     []string{"moderationStatus"},
						SourcePath:        "content/post/events.yaml",
					}},
					Privacy: &ast.PrivacyDefinition{
						ObjectID: producer.ID, SourcePath: "content/post/privacy.yaml",
						Document: ast.PrivacyDocument{FieldVisibility: []ast.PrivacyFieldVisibility{{
							Field: "moderationStatus", Visibility: tc.visibility,
						}}},
					},
				}}},
			}

			issues := validateEventGovernance(contractGraph)
			assertEventGovernanceIssueCount(
				t,
				issues,
				"CONTRACT.EVENT.PAYLOAD_FIELD_VISIBILITY_MISMATCH",
				tc.wantMismatch,
			)
		})
	}
}

func assertEventGovernanceIssueCount(
	t *testing.T,
	issues []Issue,
	code string,
	want int,
) {
	t.Helper()
	got := 0
	for _, item := range issues {
		if item.Code == code {
			got++
		}
	}
	if got != want {
		t.Fatalf("%s count = %d, want %d; issues=%#v", code, got, want, issues)
	}
}
