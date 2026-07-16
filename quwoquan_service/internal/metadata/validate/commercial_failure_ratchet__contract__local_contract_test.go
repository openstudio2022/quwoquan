package validate_test

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"testing"

	"quwoquan_service/internal/metadata/compiler"
	"quwoquan_service/internal/metadata/validate"
)

type commercialFailureBaseline struct {
	Version  int                         `json:"version"`
	Profile  string                      `json:"profile"`
	Failures []commercialFailureIdentity `json:"failures"`
}

type commercialFailureIdentity struct {
	Code       string `json:"code"`
	SubjectID  string `json:"subjectId"`
	SourcePath string `json:"sourcePath"`
}

func TestCommercialFailureSetCanOnlyShrink(t *testing.T) {
	t.Parallel()

	metadataDir := filepath.Join("..", "..", "..", "contracts", "metadata")
	_, issues, err := compiler.Validate(
		metadataDir,
		validate.ProfileCommercial,
	)
	if err != nil {
		t.Fatalf("compile commercial ContractGraph: %v", err)
	}
	baselinePath := filepath.Join(
		"..",
		"..",
		"..",
		"..",
		"specs",
		"gates",
		"contract_graph_commercial_failure_baseline.json",
	)
	raw, err := os.ReadFile(baselinePath)
	if err != nil {
		t.Fatalf("read commercial failure baseline: %v", err)
	}
	var baseline commercialFailureBaseline
	if err := json.Unmarshal(raw, &baseline); err != nil {
		t.Fatalf("decode commercial failure baseline: %v", err)
	}
	if baseline.Version != 1 ||
		baseline.Profile != string(validate.ProfileCommercial) {
		t.Fatalf("invalid commercial failure baseline header: %+v", baseline)
	}

	allowed := make(map[string]struct{}, len(baseline.Failures))
	for _, failure := range baseline.Failures {
		key := failureKey(
			failure.Code,
			failure.SubjectID,
			failure.SourcePath,
		)
		if failure.Code == "" ||
			failure.SubjectID == "" ||
			failure.SourcePath == "" {
			t.Fatalf("baseline failure identity is incomplete: %+v", failure)
		}
		if _, exists := allowed[key]; exists {
			t.Fatalf("baseline failure identity is duplicated: %s", key)
		}
		allowed[key] = struct{}{}
	}

	for _, issue := range issues {
		if issue.SubjectID == "" {
			t.Fatalf(
				"commercial issue lacks stable subject identity: %+v",
				issue,
			)
		}
		key := failureKey(issue.Code, issue.SubjectID, issue.SourcePath)
		if _, exists := allowed[key]; !exists {
			t.Fatalf(
				"commercial failure set expanded with %s: %s",
				key,
				issue.Message,
			)
		}
	}
	if len(issues) > len(baseline.Failures) {
		t.Fatalf(
			"commercial failure count grew from %d to %d",
			len(baseline.Failures),
			len(issues),
		)
	}
}

func failureKey(code, subjectID, sourcePath string) string {
	return fmt.Sprintf("%s|%s|%s", code, subjectID, sourcePath)
}
