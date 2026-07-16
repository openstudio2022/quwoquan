package graph_test

import (
	"path/filepath"
	"slices"
	"testing"

	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/load"
)

func TestProfileUpdateProposalReadinessIsDerivedAndFailsClosed(t *testing.T) {
	t.Parallel()

	metadataDir := filepath.Join("..", "..", "..", "contracts", "metadata")
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
	if !got.Modeled || !got.ContractReady || !got.Implemented {
		t.Fatalf("readiness=%+v, want implemented object packet", *got)
	}
	if got.CommercialReady || got.Stage != "implemented" {
		t.Fatalf("readiness=%+v, must remain fail-closed before UAT and four environments", *got)
	}
	for _, missing := range []string{
		"commercial.user_acceptance",
		"commercial.environment.alpha",
		"commercial.environment.beta",
		"commercial.environment.gamma",
		"commercial.environment.prod",
	} {
		if !slices.Contains(got.Missing, missing) {
			t.Fatalf("readiness missing=%v, want %s", got.Missing, missing)
		}
	}

	if len(contractGraph.ReadinessEvidence) != 1 {
		t.Fatalf("readiness evidence packets=%d, want 1", len(contractGraph.ReadinessEvidence))
	}
	for _, artifact := range contractGraph.ReadinessEvidence[0].LocalContract {
		if len(artifact.SHA256) != 64 {
			t.Fatalf("artifact %s digest=%q, want derived SHA256", artifact.Path, artifact.SHA256)
		}
	}
}
