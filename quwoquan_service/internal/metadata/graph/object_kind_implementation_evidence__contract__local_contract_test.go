package graph

import (
	"testing"

	"quwoquan_service/internal/metadata/ast"
)

func TestImplementationEvidenceFollowsSixRootKindMatrix(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name string
		kind ast.ObjectKind
	}{
		{name: "aggregate root", kind: ast.ObjectKindAggregateRoot},
		{name: "append-only fact", kind: ast.ObjectKindAppendOnlyFact},
		{name: "process manager", kind: ast.ObjectKindProcessManager},
		{name: "runtime session", kind: ast.ObjectKindRuntimeSession},
		{name: "projection", kind: ast.ObjectKindProjection},
		{name: "external reference", kind: ast.ObjectKindExternalReference},
	}
	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			evidence := minimalImplementationEvidence(test.kind)
			missing := map[string]struct{}{}
			if !implementationEvidenceReady(
				ast.Object{Kind: test.kind}, nil, nil, nil, false, evidence, missing,
			) {
				t.Fatalf("minimal kind-aware evidence rejected: %v", missing)
			}

			evidence.Service.Reader = nil
			missing = map[string]struct{}{}
			if implementationEvidenceReady(
				ast.Object{Kind: test.kind}, nil, nil, nil, false, evidence, missing,
			) {
				t.Fatal("object without its application evidence was promoted")
			}
			if _, exists := missing["implementation.service.reader"]; !exists {
				t.Fatalf("missing=%v, want service.reader", missing)
			}
		})
	}
}

func TestDomainEvidenceIsRequiredOnlyForDomainOwningKinds(t *testing.T) {
	t.Parallel()

	for _, kind := range []ast.ObjectKind{
		ast.ObjectKindAggregateRoot,
		ast.ObjectKindAppendOnlyFact,
		ast.ObjectKindProcessManager,
		ast.ObjectKindRuntimeSession,
	} {
		kind := kind
		t.Run(string(kind), func(t *testing.T) {
			t.Parallel()
			evidence := minimalImplementationEvidence(kind)
			evidence.Service.Domain = nil
			missing := map[string]struct{}{}
			if implementationEvidenceReady(
				ast.Object{Kind: kind}, nil, nil, nil, false, evidence, missing,
			) {
				t.Fatal("domain-owning object without domain evidence was promoted")
			}
			if _, exists := missing["implementation.service.domain"]; !exists {
				t.Fatalf("missing=%v, want service.domain", missing)
			}
		})
	}

	for _, kind := range []ast.ObjectKind{
		ast.ObjectKindProjection,
		ast.ObjectKindExternalReference,
	} {
		evidence := minimalImplementationEvidence(kind)
		missing := map[string]struct{}{}
		if !implementationEvidenceReady(
			ast.Object{Kind: kind}, nil, nil, nil, false, evidence, missing,
		) {
			t.Fatalf("%s was blocked by a synthetic domain obligation: %v", kind, missing)
		}
		if _, exists := missing["implementation.service.domain"]; exists {
			t.Fatalf("%s reported a synthetic domain gap: %v", kind, missing)
		}
	}
}

func TestTransportEvidenceFollowsIngressCapability(t *testing.T) {
	t.Parallel()

	t.Run("HTTP operation is ingress", func(t *testing.T) {
		t.Parallel()
		operation := ast.Operation{
			ID:   "test.sample.ReadSample",
			Kind: ast.OperationKindQuery,
		}
		evidence := minimalImplementationEvidence(ast.ObjectKindProjection)
		evidence.OperationIDs = []string{operation.ID}
		missing := map[string]struct{}{}
		if implementationEvidenceReady(
			ast.Object{Kind: ast.ObjectKindProjection},
			[]ast.Operation{operation}, nil, nil, false, evidence, missing,
		) {
			t.Fatal("HTTP object without transport evidence was promoted")
		}
		if _, exists := missing["implementation.service.transport"]; !exists {
			t.Fatalf("missing=%v, want service.transport", missing)
		}
	})

	t.Run("runtime subscription is ingress", func(t *testing.T) {
		t.Parallel()
		entrypoint := ast.RuntimeEntrypoint{
			ID:          "test.sample.ConsumeSample",
			RuntimeKind: "subscription",
		}
		evidence := minimalImplementationEvidence(ast.ObjectKindAppendOnlyFact)
		evidence.OperationIDs = []string{entrypoint.ID}
		missing := map[string]struct{}{}
		if implementationEvidenceReady(
			ast.Object{Kind: ast.ObjectKindAppendOnlyFact}, nil,
			[]ast.RuntimeEntrypoint{entrypoint}, nil, false, evidence, missing,
		) {
			t.Fatal("runtime ingress without transport evidence was promoted")
		}
		if _, exists := missing["implementation.service.transport"]; !exists {
			t.Fatalf("missing=%v, want service.transport", missing)
		}
	})

	t.Run("external port is outbound", func(t *testing.T) {
		t.Parallel()
		entrypoint := ast.RuntimeEntrypoint{
			ID:          "test.sample.InvokeProvider",
			RuntimeKind: "external_port",
		}
		evidence := minimalImplementationEvidence(ast.ObjectKindExternalReference)
		evidence.OperationIDs = []string{entrypoint.ID}
		missing := map[string]struct{}{}
		if !implementationEvidenceReady(
			ast.Object{Kind: ast.ObjectKindExternalReference}, nil,
			[]ast.RuntimeEntrypoint{entrypoint}, nil, false, evidence, missing,
		) {
			t.Fatalf("pure outbound port was treated as transport ingress: %v", missing)
		}
		if _, exists := missing["implementation.service.transport"]; exists {
			t.Fatalf("outbound port reported a transport gap: %v", missing)
		}
	})
}

func TestExternalReferenceRequiresOneConcreteImplementationSurface(t *testing.T) {
	t.Parallel()

	evidence := minimalImplementationEvidence(ast.ObjectKindExternalReference)
	evidence.Service.Store = nil
	missing := map[string]struct{}{}
	if implementationEvidenceReady(
		ast.Object{Kind: ast.ObjectKindExternalReference}, nil, nil, nil,
		false, evidence, missing,
	) {
		t.Fatal("external reference without adapters or infrastructure was promoted")
	}
	if _, exists := missing["implementation.service.store_or_transport"]; !exists {
		t.Fatalf("missing=%v, want store_or_transport", missing)
	}

	evidence.Service.Transport = []ast.EvidenceArtifact{validEvidenceArtifact("provider.go")}
	missing = map[string]struct{}{}
	if !implementationEvidenceReady(
		ast.Object{Kind: ast.ObjectKindExternalReference}, nil, nil, nil,
		false, evidence, missing,
	) {
		t.Fatalf("external reference adapter implementation rejected: %v", missing)
	}
}

func minimalImplementationEvidence(kind ast.ObjectKind) ast.ObjectReadinessEvidence {
	evidence := completeImplementationEvidence()
	evidence.Service.Domain = nil
	evidence.Service.Store = nil
	evidence.Service.Transport = nil
	switch kind {
	case ast.ObjectKindAggregateRoot,
		ast.ObjectKindAppendOnlyFact,
		ast.ObjectKindProcessManager,
		ast.ObjectKindRuntimeSession:
		evidence.Service.Domain = []ast.EvidenceArtifact{validEvidenceArtifact("domain.go")}
		evidence.Service.Store = []ast.EvidenceArtifact{validEvidenceArtifact("store.go")}
	case ast.ObjectKindProjection:
		evidence.Service.Store = []ast.EvidenceArtifact{validEvidenceArtifact("projection_store.go")}
	case ast.ObjectKindExternalReference:
		evidence.Service.Store = []ast.EvidenceArtifact{validEvidenceArtifact("provider_cache.go")}
	}
	return evidence
}
