package graph_test

import (
	"slices"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/load"
	"quwoquan_service/internal/testsupport/contractsview"
)

func TestCallerVersionPreconditionIsLimitedToSnapshotOverwriteOperations(
	t *testing.T,
) {
	t.Parallel()

	metadataDir := contractsview.Build(t)
	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatalf("load metadata: %v", err)
	}

	var got []string
	for _, operation := range graph.Build(catalog).Operations {
		if operation.Concurrency.VersionPrecondition == ast.VersionPreconditionIfMatch {
			got = append(got, operation.ID)
			found := false
			if operation.RequestBindings != nil {
				for _, binding := range operation.RequestBindings.Header {
					if binding.Name == "If-Match" &&
						binding.Field == "expectedVersion" {
						found = true
					}
				}
			}
			if !found {
				t.Errorf(
					"%s must bind generated request field expectedVersion exclusively to If-Match",
					operation.ID,
				)
			}
		}
	}
	slices.Sort(got)
	want := []string{
		"circle.circle_file.UpdateCircleFile",
		"circle.circle_group.UpdateCircleGroup",
		"ops.experiment.UpdateExperimentRollout",
	}
	if !slices.Equal(got, want) {
		t.Fatalf("caller version preconditions = %v, want %v", got, want)
	}

}
