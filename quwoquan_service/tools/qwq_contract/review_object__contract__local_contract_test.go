// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
package main

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

const reviewTestSourceHash = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

func reviewTestGraph(readiness []graph.ObjectReadiness, evidence []ast.ObjectReadinessEvidence) *graph.ContractGraph {
	contractGraph := &graph.ContractGraph{
		ObjectReadiness:   readiness,
		ReadinessEvidence: evidence,
		Sources: []ast.SourceDigest{{
			Path:   "content/content/post/object.yaml",
			SHA256: reviewTestSourceHash,
		}},
	}
	seen := make(map[string]struct{}, len(readiness))
	for _, objectReadiness := range readiness {
		if _, duplicate := seen[objectReadiness.ObjectID]; duplicate {
			continue
		}
		seen[objectReadiness.ObjectID] = struct{}{}
		contractGraph.Objects = append(contractGraph.Objects, ast.Object{
			ID:         objectReadiness.ObjectID,
			Kind:       ast.ObjectKindAggregateRoot,
			SourcePath: strings.ReplaceAll(objectReadiness.ObjectID, ".", "/") + "/object.yaml",
		})
	}
	return contractGraph
}

func TestReviewObjectProfilesUseExactReadinessStage(t *testing.T) {
	readiness := graph.ObjectReadiness{
		ObjectID:        "content.post",
		Stage:           "implemented",
		Modeled:         true,
		ContractReady:   true,
		Implemented:     true,
		CommercialReady: true, // Static graph must not bypass trusted dynamic closure.
		Missing:         []string{"implementation.outbox", "implementation.outbox"},
	}
	for _, testCase := range []struct {
		name    string
		profile reviewObjectProfile
		status  string
		checkID string
		missing []string
	}{
		{name: "model", profile: reviewObjectProfileModel, status: "PASS", checkID: "object.model", missing: []string{"implementation.outbox"}},
		{name: "contract", profile: reviewObjectProfileContract, status: "PASS", checkID: "object.contract", missing: []string{"implementation.outbox"}},
		{name: "implementation", profile: reviewObjectProfileImplementation, status: "PASS", checkID: "object.implementation", missing: []string{"implementation.outbox"}},
		{name: "commercial", profile: reviewObjectProfileCommercial, status: "BLOCK", checkID: "object.commercial", missing: []string{"commercial.result_bundle", "implementation.outbox"}},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			result := reviewReadiness(
				readiness,
				testCase.profile,
				reviewTestSourceHash,
				reviewEvidenceSummary{},
				1,
			)
			if result.Status != testCase.status {
				t.Fatalf("status = %q, want %q", result.Status, testCase.status)
			}
			if result.CheckID != testCase.checkID {
				t.Fatalf("checkId = %q, want %q", result.CheckID, testCase.checkID)
			}
			if strings.Join(result.Missing, ",") != strings.Join(testCase.missing, ",") {
				t.Fatalf("missing = %v, want %v", result.Missing, testCase.missing)
			}
		})
	}
}

func TestReviewObjectResultIsByteStable(t *testing.T) {
	contractGraph := reviewTestGraph([]graph.ObjectReadiness{{
		ObjectID:      "content.post",
		Stage:         "contract-ready",
		Modeled:       true,
		ContractReady: true,
		Missing:       []string{"zeta", "alpha", "zeta"},
	}}, nil)

	first, err := reviewCompiledObject(contractGraph, "content.post", reviewObjectProfileContract)
	if err != nil {
		t.Fatalf("first review: %v", err)
	}
	second, err := reviewCompiledObject(contractGraph, "content.post", reviewObjectProfileContract)
	if err != nil {
		t.Fatalf("second review: %v", err)
	}
	firstBytes, err := json.MarshalIndent(first, "", "  ")
	if err != nil {
		t.Fatalf("marshal first result: %v", err)
	}
	secondBytes, err := json.MarshalIndent(second, "", "  ")
	if err != nil {
		t.Fatalf("marshal second result: %v", err)
	}
	if !bytes.Equal(firstBytes, secondBytes) {
		t.Fatalf("review-object output is not byte-stable:\nfirst=%s\nsecond=%s", firstBytes, secondBytes)
	}
	previousIndex := -1
	for _, field := range []string{
		`"objectId"`, `"checkId"`, `"profile"`, `"contractGraphSourceHash"`,
		`"status"`, `"stage"`, `"evidenceSummary"`, `"missing"`,
	} {
		index := bytes.Index(firstBytes, []byte(field))
		if index == -1 {
			t.Fatalf("stable JSON misses %s: %s", field, firstBytes)
		}
		if index <= previousIndex {
			t.Fatalf("stable JSON field order is not deterministic at %s: %s", field, firstBytes)
		}
		previousIndex = index
	}
	if !bytes.Contains(firstBytes, []byte(`"checkId": "object.contract"`)) ||
		!bytes.Contains(firstBytes, []byte(`"contractGraphSourceHash"`)) {
		t.Fatalf("stable JSON misses contract check identity: %s", firstBytes)
	}
}

func TestReviewObjectCLIExitsNonZeroAfterEmittingBlockedReceipt(t *testing.T) {
	for _, testCase := range []struct {
		name    string
		payload any
		blocked bool
		want    string
	}{
		{
			name: "exact pass",
			payload: reviewObjectResult{
				ObjectID: "content.post", Profile: reviewObjectProfileImplementation,
				Status: "PASS", Stage: "implemented",
			},
		},
		{
			name: "exact commercial block",
			payload: reviewObjectResult{
				ObjectID: "content.post", Profile: reviewObjectProfileCommercial,
				Status: "BLOCK", Stage: "implemented",
				Missing: []string{"commercial.result_bundle"},
			},
			blocked: true,
			want:    "review-object commercial blocked for content.post",
		},
		{
			name: "all preserves actual statuses",
			payload: reviewObjectBundle{
				Profile: reviewObjectProfileContract,
				Objects: []reviewObjectResult{
					{ObjectID: "content.ready", Profile: reviewObjectProfileContract, Status: "PASS"},
					{ObjectID: "content.blocked", Profile: reviewObjectProfileContract, Status: "BLOCK"},
				},
			},
			blocked: true,
			want:    "review-object contract blocked for 1 object(s)",
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			var stdout bytes.Buffer
			err := emitReviewObjectPayload(&stdout, testCase.payload)
			if testCase.blocked {
				if err == nil || err.Error() != testCase.want {
					t.Fatalf("blocked receipt error = %v, want %q", err, testCase.want)
				}
			} else if err != nil {
				t.Fatalf("passing receipt returned error: %v", err)
			}
			if stdout.Len() == 0 || !json.Valid(stdout.Bytes()) {
				t.Fatalf("review receipt was not emitted as valid JSON: %q", stdout.String())
			}
		})
	}
}

func TestReviewAllSortsObjectsAndIsByteStable(t *testing.T) {
	contractGraph := reviewTestGraph([]graph.ObjectReadiness{
		{ObjectID: "content.zeta", Stage: "modeled", Modeled: true},
		{ObjectID: "content.alpha", Stage: "contract-ready", Modeled: true, ContractReady: true},
	}, nil)
	first, err := reviewCompiledObjects(contractGraph, reviewObjectProfileContract)
	if err != nil {
		t.Fatalf("first review all: %v", err)
	}
	second, err := reviewCompiledObjects(contractGraph, reviewObjectProfileContract)
	if err != nil {
		t.Fatalf("second review all: %v", err)
	}
	if len(first.Objects) != 2 || first.Objects[0].ObjectID != "content.alpha" || first.Objects[1].ObjectID != "content.zeta" {
		t.Fatalf("all objects are not objectId-sorted: %v", first.Objects)
	}
	for _, result := range first.Objects {
		if result.ContractGraphSourceHash != first.ContractGraphSourceHash {
			t.Fatalf("bundle object source hash = %q, want bundle hash %q", result.ContractGraphSourceHash, first.ContractGraphSourceHash)
		}
	}
	firstBytes, err := json.MarshalIndent(first, "", "  ")
	if err != nil {
		t.Fatalf("marshal first bundle: %v", err)
	}
	secondBytes, err := json.MarshalIndent(second, "", "  ")
	if err != nil {
		t.Fatalf("marshal second bundle: %v", err)
	}
	if !bytes.Equal(firstBytes, secondBytes) {
		t.Fatalf("review-object --all output is not byte-stable:\nfirst=%s\nsecond=%s", firstBytes, secondBytes)
	}
}

func TestReviewObjectRejectsUnknownExactObject(t *testing.T) {
	_, err := reviewCompiledObject(reviewTestGraph(nil, nil), "content.post", reviewObjectProfileModel)
	if err == nil || !strings.Contains(err.Error(), "is not present") {
		t.Fatalf("unknown exact object must fail, got %v", err)
	}
}

func TestReviewObjectFailsClosedWhenSourceHashCannotBeDerived(t *testing.T) {
	_, err := reviewCompiledObject(&graph.ContractGraph{
		Objects: []ast.Object{{ID: "content.post", Kind: ast.ObjectKindAggregateRoot}},
		ObjectReadiness: []graph.ObjectReadiness{{
			ObjectID: "content.post", Modeled: true,
		}},
	}, "content.post", reviewObjectProfileModel)
	if err == nil || !strings.Contains(err.Error(), "source hash") {
		t.Fatalf("missing source identity must fail closed, got %v", err)
	}
}

func TestReviewObjectRequiresOneToOneObjectReadinessIndex(t *testing.T) {
	base := graph.ObjectReadiness{ObjectID: "content.post", Modeled: true}
	for name, contractGraph := range map[string]*graph.ContractGraph{
		"missing readiness": {
			Objects: []ast.Object{{ID: "content.post", Kind: ast.ObjectKindAggregateRoot}},
			Sources: []ast.SourceDigest{{Path: "content/post/object.yaml", SHA256: reviewTestSourceHash}},
		},
		"duplicate readiness": reviewTestGraph(
			[]graph.ObjectReadiness{base, base},
			nil,
		),
		"orphan readiness": {
			ObjectReadiness: []graph.ObjectReadiness{base},
			Sources:         []ast.SourceDigest{{Path: "content/post/object.yaml", SHA256: reviewTestSourceHash}},
		},
		"duplicate object": func() *graph.ContractGraph {
			candidate := reviewTestGraph([]graph.ObjectReadiness{base}, nil)
			candidate.Objects = append(candidate.Objects, candidate.Objects[0])
			return candidate
		}(),
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := reviewCompiledObject(contractGraph, "content.post", reviewObjectProfileModel); err == nil {
				t.Fatal("exact review accepted a non-bijective object/readiness index")
			}
			if _, err := reviewCompiledObjects(contractGraph, reviewObjectProfileModel); err == nil {
				t.Fatal("--all review accepted a non-bijective object/readiness index")
			}
		})
	}
}

func TestReviewEvidenceSummaryUsesOnlyUniquePacket(t *testing.T) {
	readiness := graph.ObjectReadiness{
		ObjectID: "content.post", Stage: "implemented", Modeled: true,
		ContractReady: true, Implemented: true,
	}
	unique := ast.ObjectReadinessEvidence{
		ObjectID: "content.post",
		Service: ast.ServiceStructureEvidence{
			Domain: []ast.EvidenceArtifact{{Path: "service/domain.go"}},
			Store:  []ast.EvidenceArtifact{{Path: "service/store.go"}},
		},
		App: ast.AppStructureEvidence{
			Application:     []ast.EvidenceArtifact{{Path: "app/application.dart"}},
			PageParticipant: true,
			PageOwned:       true,
		},
		Ops: ast.OpsStructureEvidence{
			RollbackRunner: []ast.EvidenceArtifact{{Path: "ops/rollback.py"}},
		},
	}
	result, err := reviewCompiledObject(
		reviewTestGraph([]graph.ObjectReadiness{readiness}, []ast.ObjectReadinessEvidence{unique}),
		"content.post",
		reviewObjectProfileImplementation,
	)
	if err != nil {
		t.Fatalf("review unique evidence: %v", err)
	}
	if result.Status != "PASS" || result.EvidenceSummary.Service.EntryCount != 2 ||
		result.EvidenceSummary.App.EntryCount != 1 || result.EvidenceSummary.Ops.EntryCount != 1 ||
		!result.EvidenceSummary.PageParticipant || !result.EvidenceSummary.PageOwned {
		t.Fatalf("unique evidence summary = %#v, result = %#v", result.EvidenceSummary, result)
	}
	for _, testCase := range []struct {
		evidence []ast.ObjectReadinessEvidence
		missing  string
	}{
		{evidence: nil, missing: "readiness.evidence"},
		{evidence: []ast.ObjectReadinessEvidence{unique, unique}, missing: "readiness.evidence.duplicate"},
	} {
		blocked, reviewErr := reviewCompiledObject(
			reviewTestGraph([]graph.ObjectReadiness{readiness}, testCase.evidence),
			"content.post",
			reviewObjectProfileImplementation,
		)
		if reviewErr != nil || blocked.Status != "BLOCK" ||
			blocked.EvidenceSummary != (reviewEvidenceSummary{}) {
			t.Fatalf("invalid evidence packet result = %#v, error = %v", blocked, reviewErr)
		}
		if !strings.Contains(strings.Join(blocked.Missing, ","), testCase.missing) {
			t.Fatalf("invalid evidence missing = %v, want %q", blocked.Missing, testCase.missing)
		}
	}
}

func TestReviewObjectRequiresExactlyOneSelectorAndRepoRoot(t *testing.T) {
	for _, testCase := range []struct {
		name string
		args []string
		want string
	}{
		{name: "missing selector", args: []string{"review-object", "--repo-root", t.TempDir()}, want: "exactly one"},
		{name: "missing repo root", args: []string{"review-object", "--object", "content.post"}, want: "--repo-root is required"},
		{name: "mutually exclusive", args: []string{"review-object", "--repo-root", t.TempDir(), "--object", "content.post", "--all"}, want: "mutually exclusive"},
		{name: "unsupported format", args: []string{"review-object", "--repo-root", t.TempDir(), "--object", "content.post", "--format", "text"}, want: "unsupported review-object format"},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			var stdout bytes.Buffer
			err := run(testCase.args, &stdout)
			if err == nil || !strings.Contains(err.Error(), testCase.want) {
				t.Fatalf("run(%v) error = %v, want %q", testCase.args, err, testCase.want)
			}
			if stdout.Len() != 0 {
				t.Fatalf("failed review-object must not emit stdout: %s", stdout.String())
			}
		})
	}
	for _, args := range [][]string{
		{"review-object", "--all"},
	} {
		err := run(args, &bytes.Buffer{})
		if err == nil {
			t.Fatalf("run(%v) unexpectedly succeeded", args)
		}
	}
}

func TestReviewObjectRejectsInvalidGlobalGraphWithoutWritingJSON(t *testing.T) {
	metadataDir := t.TempDir()
	var stdout bytes.Buffer
	for _, selector := range [][]string{{"--object", "content.post"}, {"--all"}} {
		stdout.Reset()
		args := append([]string{
			"review-object",
			"--metadata-dir", metadataDir,
			"--repo-root", t.TempDir(),
		}, selector...)
		err := run(args, &stdout)
		if err == nil {
			t.Fatal("invalid global ContractGraph must fail closed")
		}
		if stdout.Len() != 0 {
			t.Fatalf("invalid global ContractGraph must not emit a target verdict: %s", stdout.String())
		}
	}
}
