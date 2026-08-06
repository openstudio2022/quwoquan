// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
package validate

import (
	"testing"

	"quwoquan_service/internal/metadata/ast"
)

func TestLifecycleOwnedRecoveryCommandRequiresCanonicalConsumerObject(t *testing.T) {
	t.Parallel()

	object := ast.Object{
		ID:     "search.search_request_fact",
		Domain: "search",
		Name:   "SearchRequestFact",
		Kind:   ast.ObjectKindAppendOnlyFact,
		Lifecycle: &ast.LifecycleDefinition{
			SourceEvents: []string{"user.user_account.UserAccountClosed"},
			EventConsumers: []ast.LifecycleEventConsumer{{
				Name: "ApplySearchRequestAccountClosure", Kind: "subscription",
				Facet: "UserAccountClosedProjection", Method: "applyUserAccountClosed",
				Idempotency: "event_id",
			}},
		},
	}
	operation := canonicalLifecycleRecoveryOperation()
	objects := map[string]ast.Object{object.ID: object}
	byDomainName := map[string]ast.Object{
		domainObjectKey(object.Domain, object.Name): object,
	}
	issues := validateCommercialOperation(operation, objects, byDomainName, nil)
	for _, code := range []string{
		"CONTRACT.OPERATION.INVALID_COMMAND_OWNER_KIND",
		"CONTRACT.OPERATION.INVALID_APPEND_SINK_KIND",
		"CONTRACT.OPERATION.LIFECYCLE_OWNER_WITHOUT_CONSUMER",
	} {
		if lifecycleOwnerIssuePresent(issues, code) {
			t.Fatalf("canonical lifecycle-owned command raised %s: %+v", code, issues)
		}
	}

	object.Lifecycle = nil
	byDomainName[domainObjectKey(object.Domain, object.Name)] = object
	issues = validateCommercialOperation(operation, objects, byDomainName, nil)
	if !lifecycleOwnerIssuePresent(issues, "CONTRACT.OPERATION.LIFECYCLE_OWNER_WITHOUT_CONSUMER") {
		t.Fatalf("lifecycle owner without authored consumer was accepted: %+v", issues)
	}
}

func canonicalLifecycleRecoveryOperation() ast.Operation {
	return ast.Operation{
		ID:      "search.search_request_fact.RecoverSearchAccountClosureDeadLetter",
		LocalID: "RecoverSearchAccountClosureDeadLetter",
		Domain:  "search", ObjectID: "search.search_request_fact",
		Method: "POST", Kind: ast.OperationKindCommand, KindExplicit: true,
		Facet:        "SearchRequestAccountClosureRecoveryCommandFacet",
		FacadeMethod: "recoverDeadLetter", LifecycleOwner: "SearchRequestFact",
		MutationTarget: "SearchRequestFact", InvariantTarget: "SearchRequestFact",
		ActorRequirement: "none", AuthMode: "required", Principal: "operator",
		OwnershipPolicy: "service_owned_projection_delivery",
		Commercial:      ast.CommercialBinding{Status: "ready", Explicit: true},
		Reliability: ast.ReliabilityPolicy{
			TimeoutMilliseconds: 1500, Cancellation: "supported",
			RetryMode: "idempotent", MaxAttempts: 2, Idempotency: "required",
		},
		ErrorCodes: []string{"SEARCH.SYSTEM.internal_error"},
		Privacy: ast.PrivacyPolicy{
			RequestClassification: "INTERNAL", ResponseClassification: "INTERNAL",
			LogPolicy: "metadata_only",
		},
		Telemetry: ast.TelemetryPolicy{Metric: "search_account_closure_dead_letter_recover", Trace: true},
		SLO:       ast.SLOPolicy{LatencyP95Milliseconds: 500, AvailabilityPercent: 99.9},
	}
}

func lifecycleOwnerIssuePresent(issues []Issue, code string) bool {
	for _, issue := range issues {
		if issue.Code == code {
			return true
		}
	}
	return false
}
