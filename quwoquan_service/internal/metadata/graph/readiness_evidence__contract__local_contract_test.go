// spec_ref: specs/feature-tree/runtime/runtime-control-plane-foundation/domain-onboarding-acceptance-governance/spec.md#gwt-001
package graph

import (
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
)

func TestCoverageReportsCumulativeReadinessInsteadOfExclusiveStages(t *testing.T) {
	t.Parallel()

	contractGraph := &ContractGraph{
		Objects: []ast.Object{{ID: "test.one"}, {ID: "test.two"}, {ID: "test.three"}},
		ReadinessEvidence: []ast.ObjectReadinessEvidence{
			{ObjectID: "test.two"},
			{ObjectID: "test.two"},
		},
		ObjectReadiness: []ObjectReadiness{
			{ObjectID: "test.one", Stage: "modeled", Modeled: true},
			{
				ObjectID: "test.two", Stage: "implemented", Modeled: true,
				ContractReady: true, Implemented: true,
			},
			{
				ObjectID: "test.three", Stage: "commercial-ready", Modeled: true,
				ContractReady: true, Implemented: true, CommercialReady: true,
			},
		},
	}

	coverage := contractGraph.Coverage()
	if coverage.ReadinessEvidencePackets != 2 || coverage.ReadinessEvidenceObjects != 1 {
		t.Fatalf("evidence coverage=%+v, want two packets bound to one object", coverage)
	}
	if coverage.ReadinessModeled != 3 || coverage.ReadinessContractReady != 2 ||
		coverage.ReadinessImplemented != 2 || coverage.ReadinessCommercialReady != 1 {
		t.Fatalf("cumulative readiness=%+v", coverage)
	}
	if coverage.ObjectsByReadiness["modeled"] != 1 ||
		coverage.ObjectsByReadiness["implemented"] != 1 ||
		coverage.ObjectsByReadiness["commercial-ready"] != 1 {
		t.Fatalf("exclusive stage distribution=%v", coverage.ObjectsByReadiness)
	}
}

func TestCoverageExcludesInfrastructureProbesFromPublicOperations(t *testing.T) {
	t.Parallel()

	for _, path := range []string{
		"/health", "/healthz", "/readyz", "/metrics", "/livez", "/startupz",
	} {
		if isPublicTransportPath(path) {
			t.Errorf("infrastructure probe %q counted as a public business operation", path)
		}
	}
	if !isPublicTransportPath("/content/posts") {
		t.Fatal("public business route was excluded from public operations")
	}
}

func TestImplementationEvidenceRequiresExactOperationsAndContentDigests(t *testing.T) {
	t.Parallel()

	operation := ast.Operation{
		ID: "test.sample.CreateSample", LocalID: "CreateSample",
		Kind: ast.OperationKindCommand,
	}
	evidence := completeImplementationEvidence(operation.ID)
	missing := map[string]struct{}{}
	if !implementationEvidenceReady(
		ast.Object{Kind: ast.ObjectKindAggregateRoot},
		[]ast.Operation{operation},
		nil,
		evidence,
		missing,
	) {
		t.Fatalf("complete evidence rejected: %v", missing)
	}

	evidence.OperationIDs = nil
	missing = map[string]struct{}{}
	if implementationEvidenceReady(
		ast.Object{Kind: ast.ObjectKindAggregateRoot},
		[]ast.Operation{operation},
		nil,
		evidence,
		missing,
	) {
		t.Fatal("evidence without operation coverage was accepted")
	}
	if _, exists := missing["implementation.operation_coverage"]; !exists {
		t.Fatalf("missing=%v, want operation coverage failure", missing)
	}

	evidence = completeImplementationEvidence(operation.ID)
	evidence.LocalContract[0].SHA256 = "not-a-content-digest"
	missing = map[string]struct{}{}
	if implementationEvidenceReady(
		ast.Object{Kind: ast.ObjectKindAggregateRoot},
		[]ast.Operation{operation},
		nil,
		evidence,
		missing,
	) {
		t.Fatal("evidence with an invalid digest was accepted")
	}
	if _, exists := missing["implementation.local_contract"]; !exists {
		t.Fatalf("missing=%v, want local contract digest failure", missing)
	}
}

func TestDuplicateEvidenceCannotPromoteObject(t *testing.T) {
	t.Parallel()

	evidence := completeImplementationEvidence("test.sample.ProjectSample")
	contractGraph := Build(&ast.Catalog{
		Objects: []ast.Object{{
			ID: "test.sample", Domain: "test", Name: "Sample",
			Kind: ast.ObjectKindProjection, KindExplicit: true,
		}},
		RuntimeEntrypoints: []ast.RuntimeEntrypoint{{
			ID: "test.sample.ProjectSample", LocalID: "ProjectSample",
			Domain: "test", ObjectID: "test.sample", RuntimeKind: "projector",
			Phase: "event_projection", ApplicationKind: ast.OperationKindCommand,
			Facet: "SampleProjector", FacadeMethod: "apply", ObjectOwner: "Sample",
			SourceEvents: []string{"test.SampleObserved"}, Checkpoint: "sample_sequence",
			Rebuild: "replay_sample_events", Tombstone: "delete_sample_keep_checkpoint",
			Idempotency: "aggregate_version",
		}},
		BusinessObjectMaps: []ast.BusinessObjectMap{{
			Domain:  "test",
			Objects: []ast.BusinessObjectBoundary{{CanonicalObject: "Sample"}},
		}},
		ReadinessEvidence: []ast.ObjectReadinessEvidence{evidence, evidence},
	})

	readiness := contractGraph.ObjectReadiness[0]
	if readiness.Implemented || readiness.Stage != "contract-ready" {
		t.Fatalf("duplicate evidence promoted object: %+v", readiness)
	}
	if len(readiness.Missing) != 1 || readiness.Missing[0] != "readiness.evidence.duplicate" {
		t.Fatalf("missing=%v, want duplicate evidence failure", readiness.Missing)
	}
}

func TestCommercialEvidenceCannotOverrideBlockedOperation(t *testing.T) {
	t.Parallel()

	evidence := ast.ObjectReadinessEvidence{
		UserAcceptance: []ast.EvidenceArtifact{validEvidenceArtifact("uat.json")},
		Environments: []ast.EnvironmentEvidence{
			{Name: "alpha", Artifact: validEvidenceArtifact("alpha.json")},
			{Name: "beta", Artifact: validEvidenceArtifact("beta.json")},
			{Name: "gamma", Artifact: validEvidenceArtifact("gamma.json")},
			{Name: "prod", Artifact: validEvidenceArtifact("prod.json")},
		},
	}
	operation := ast.Operation{
		LocalID:    "CreateSample",
		Commercial: ast.CommercialBinding{Status: "blocked"},
	}
	missing := map[string]struct{}{}
	if commercialEvidenceReady([]ast.Operation{operation}, evidence, missing) {
		t.Fatal("blocked operation was promoted to commercial-ready")
	}
	if _, exists := missing["commercial.operation.CreateSample"]; !exists {
		t.Fatalf("missing=%v, want blocked operation failure", missing)
	}

	operation.Commercial.Status = "ready"
	missing = map[string]struct{}{}
	if !commercialEvidenceReady([]ast.Operation{operation}, evidence, missing) {
		t.Fatalf("ready operation with complete evidence rejected: %v", missing)
	}
}

func completeImplementationEvidence(operationIDs ...string) ast.ObjectReadinessEvidence {
	return ast.ObjectReadinessEvidence{
		ObjectID:       "test.sample",
		OperationIDs:   operationIDs,
		DomainBehavior: []ast.EvidenceArtifact{validEvidenceArtifact("domain.go")},
		Store:          []ast.EvidenceArtifact{validEvidenceArtifact("store.go")},
		Outbox:         []ast.EvidenceArtifact{validEvidenceArtifact("outbox.go")},
		Transport:      []ast.EvidenceArtifact{validEvidenceArtifact("handler.go")},
		LocalContract:  []ast.EvidenceArtifact{validEvidenceArtifact("local.xml")},
		APIIntegration: []ast.EvidenceArtifact{validEvidenceArtifact("api.xml")},
		SourcePath:     "evidence/object.json",
	}
}

func validEvidenceArtifact(path string) ast.EvidenceArtifact {
	return ast.EvidenceArtifact{Path: path, SHA256: strings.Repeat("a", 64)}
}
