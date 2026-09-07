package graph_test

import (
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/load"
	"quwoquan_service/internal/metadata/validate"
	"quwoquan_service/internal/testsupport/contractsview"
)

// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/unified-entry-security/rate-limit-protection/spec.md#gwt-001
func TestCanonicalSharedAdmissionRuntimeEntrypointConsistencySurvivesLoadBuildAndSchema(t *testing.T) {
	metadataDir := contractsview.Build(t)
	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatalf("load canonical metadata: %v", err)
	}
	contractGraph := graph.Build(catalog)

	var sharedAdmission *ast.RuntimeEntrypoint
	for index := range contractGraph.RuntimeEntrypoints {
		if contractGraph.RuntimeEntrypoints[index].ID == "gateway.rate_limit_bucket.SharedAdmission" {
			sharedAdmission = &contractGraph.RuntimeEntrypoints[index]
			break
		}
	}
	if sharedAdmission == nil {
		t.Fatal("canonical SharedAdmission runtime entrypoint missing from ContractGraph")
	}
	if sharedAdmission.RuntimeKind != "middleware" ||
		sharedAdmission.ApplicationKind != ast.OperationKindSession {
		t.Fatalf("unexpected SharedAdmission runtime seam: %+v", sharedAdmission)
	}
	if sharedAdmission.Consistency == nil ||
		sharedAdmission.Consistency.Arbitration != "conditional_admission" {
		t.Fatalf("SharedAdmission consistency lost during load/build: %+v", sharedAdmission.Consistency)
	}
	if err := validate.ContractGraphSchema(metadataDir, contractGraph); err != nil {
		t.Fatalf("canonical ContractGraph schema rejected SharedAdmission consistency: %v", err)
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestRuntimeEntrypointContractGraphSchemaConstrainsConsistencyByApplicationKind(t *testing.T) {
	for _, test := range []struct {
		name            string
		applicationKind ast.OperationKind
		consistency     ast.OperationConsistency
		wantAccepted    bool
	}{
		{
			name:            "session accepts arbitration",
			applicationKind: ast.OperationKindSession,
			consistency:     ast.OperationConsistency{Arbitration: "conditional_admission"},
			wantAccepted:    true,
		},
		{
			name:            "session rejects command atomic commit",
			applicationKind: ast.OperationKindSession,
			consistency:     ast.OperationConsistency{AtomicCommit: boolPointer(true)},
		},
		{
			name:            "command accepts atomic commit",
			applicationKind: ast.OperationKindCommand,
			consistency:     ast.OperationConsistency{AtomicCommit: boolPointer(true), Arbitration: "unique_winner"},
			wantAccepted:    true,
		},
		{
			name:            "command rejects query freshness",
			applicationKind: ast.OperationKindCommand,
			consistency:     ast.OperationConsistency{Source: "projection", Freshness: "eventual"},
		},
		{
			name:            "query accepts bounded freshness",
			applicationKind: ast.OperationKindQuery,
			consistency: ast.OperationConsistency{
				Source: "projection", Freshness: "bounded", MaxStalenessSeconds: 30, StaleResult: "with_watermark",
			},
			wantAccepted: true,
		},
		{
			name:            "query rejects arbitration",
			applicationKind: ast.OperationKindQuery,
			consistency:     ast.OperationConsistency{Arbitration: "version_cas"},
		},
		{
			name:            "query bounded requires staleness bound",
			applicationKind: ast.OperationKindQuery,
			consistency:     ast.OperationConsistency{Source: "projection", Freshness: "bounded"},
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			metadataDir := t.TempDir()
			writeSchemas(t, metadataDir)
			entrypoint := ast.RuntimeEntrypoint{
				ID: "gateway.rate_limit_bucket.SharedAdmission", LocalID: "SharedAdmission",
				Domain: "gateway", ObjectID: "gateway.rate_limit_bucket",
				RuntimeKind: "middleware", Phase: "post_authorization_pre_owner_proxy",
				ApplicationKind: test.applicationKind, Facet: "RateLimitAdmissionFacade",
				FacadeMethod: "admit", ObjectOwner: "RateLimitBucket",
				Consistency: &test.consistency,
				Telemetry:   ast.TelemetryPolicy{Metric: "api_edge_admission_decisions_total", Trace: true},
				SLO:         ast.RuntimeEntrypointSLO{LatencyP95Milliseconds: 20, FailureRatioPercent: 0.1},
				SourcePath:  "gateway/edge_security/rate_limit_bucket/operations.yaml",
			}
			err := validate.ContractGraphSchema(metadataDir, contractGraphWithRuntimeEntrypoint(entrypoint))
			if test.wantAccepted && err != nil {
				t.Fatalf("valid %s consistency rejected: %v", test.applicationKind, err)
			}
			if !test.wantAccepted && err == nil {
				t.Fatalf("invalid %s consistency accepted: %+v", test.applicationKind, test.consistency)
			}
		})
	}
}

func boolPointer(value bool) *bool {
	return &value
}

func contractGraphWithRuntimeEntrypoint(entrypoint ast.RuntimeEntrypoint) *graph.ContractGraph {
	return &graph.ContractGraph{
		Objects:            []ast.Object{},
		Operations:         []ast.Operation{},
		RuntimeEntrypoints: []ast.RuntimeEntrypoint{entrypoint},
		Projections:        []ast.Projection{},
		BusinessObjectMaps: []ast.BusinessObjectMap{},
		ReadinessCases:     []ast.ReadinessCaseContract{},
		ReadinessEvidence:  []ast.ObjectReadinessEvidence{},
		ObjectReadiness:    []graph.ObjectReadiness{},
		Sources:            []ast.SourceDigest{},
		Documents:          []ast.SourceDocument{},
	}
}
