package graph_test

import (
	"os"
	"path/filepath"
	"regexp"
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

	callerVersionField := regexp.MustCompile(
		`(?mi)(?:name:\s*expected[a-z0-9_]*version|request_fields:\s*\[[^\]]*expected[a-z0-9_]*version)`,
	)
	var bodyVersionFiles []string
	if err := filepath.WalkDir(
		metadataDir,
		func(path string, entry os.DirEntry, walkErr error) error {
			if walkErr != nil {
				return walkErr
			}
			if entry.IsDir() || filepath.Ext(entry.Name()) != ".yaml" {
				return nil
			}
			content, readErr := os.ReadFile(path)
			if readErr != nil {
				return readErr
			}
			if callerVersionField.Match(content) {
				relative, relativeErr := filepath.Rel(metadataDir, path)
				if relativeErr != nil {
					return relativeErr
				}
				bodyVersionFiles = append(bodyVersionFiles, relative)
			}
			return nil
		},
	); err != nil {
		t.Fatalf("scan service contracts: %v", err)
	}
	if len(bodyVersionFiles) != 0 {
		t.Fatalf(
			"public request contracts must use typed concurrency instead of caller version fields: %v",
			bodyVersionFiles,
		)
	}
}
