package graph_test

import (
	"testing"

	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/load"
	"quwoquan_service/internal/testsupport/contractsview"
)

func TestProfileUpdateProposalReadinessHasNoManualEvidenceDeclaration(t *testing.T) {
	t.Parallel()

	metadataDir := contractsview.Build(t)
	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatalf("load metadata: %v", err)
	}
	contractGraph := graph.Build(catalog)

	var got *graph.ObjectReadiness
	for index := range contractGraph.ObjectReadiness {
		if contractGraph.ObjectReadiness[index].ObjectID == "user.profile_update_proposal" {
			got = &contractGraph.ObjectReadiness[index]
			break
		}
	}
	if got == nil {
		t.Fatal("ProfileUpdateProposal derived readiness is missing")
	}
	if !got.Modeled || !got.ContractReady {
		t.Fatalf("readiness=%+v, want modeled contract-ready object", *got)
	}
	if got.Implemented || got.CommercialReady || got.Stage != "contract-ready" {
		t.Fatalf("readiness=%+v, runtime evidence must stay external to metadata", *got)
	}
	if len(got.Missing) != 1 || got.Missing[0] != "readiness.evidence" {
		t.Fatalf("readiness missing=%v, want derived runner evidence only", got.Missing)
	}
	if len(contractGraph.ReadinessEvidence) != 0 {
		t.Fatalf("metadata must not carry manual readiness evidence: %+v", contractGraph.ReadinessEvidence)
	}
}
