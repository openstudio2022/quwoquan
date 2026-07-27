package reliabletask

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestDataContentTreeMerkleMatchesPythonContractVector(t *testing.T) {
	root := t.TempDir()
	if err := os.Mkdir(filepath.Join(root, "sub"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "a.txt"), []byte("alpha"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "sub", "b.txt"), []byte("beta"), 0o644); err != nil {
		t.Fatal(err)
	}
	digest, err := dataContentTreeMerkle(root)
	if err != nil {
		t.Fatal(err)
	}
	const pythonDigest = "sha256:a15e6363ca02c71506b09fa0af608b7ce5d3d788c29fe5d34bf1190479dc4a8e"
	if digest != pythonDigest {
		t.Fatalf("Go/Python canonical Merkle drift: got=%s want=%s", digest, pythonDigest)
	}
}

func TestDataContentFilesystemEvidenceVerifierBindsAppliedTransactionAndCanonicalObject(
	t *testing.T,
) {
	root := t.TempDir()
	publishRoot := filepath.Join(root, "publish")
	evidenceRoot := filepath.Join(root, "evidence")
	canonicalRef := "entities/地点/景区/真实地点"
	canonicalRoot := filepath.Join(publishRoot, filepath.FromSlash(canonicalRef))
	if err := os.MkdirAll(canonicalRoot, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(
		filepath.Join(canonicalRoot, "page.md"),
		[]byte("# 真实地点\n"),
		0o644,
	); err != nil {
		t.Fatal(err)
	}
	digest, err := dataContentTreeMerkle(canonicalRoot)
	if err != nil {
		t.Fatal(err)
	}
	const transactionID = "txn-real-object"
	applyRef := filepath.ToSlash(filepath.Join(transactionID, "apply_report.json"))
	writeDataContentApplyFixture(t, filepath.Join(evidenceRoot, filepath.FromSlash(applyRef)), map[string]string{
		"schema":              dataContentObjectTransactionApplySchema,
		"status":              "applied",
		"transactionId":       transactionID,
		"executionId":         "20260711--travel-homepage-coverage--cn-test--canary-001",
		"objectKind":          "entities",
		"objectRef":           "地点/景区/真实地点",
		"objectClosureDigest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
	})
	item := DataContentWorkItem{
		ExecutionID: "20260711--travel-homepage-coverage--cn-test--canary-001",
		JobID:       "job-001",
		Stage:       "publish",
	}
	result := DataContentExecutionResult{
		ExecutionID:           item.ExecutionID,
		JobID:                 item.JobID,
		CanonicalObjectRef:    canonicalRef,
		CanonicalObjectSHA256: digest,
		ObjectTransactionID:   transactionID,
		ResultEnvelopeRef:     applyRef,
		AcceptanceClass:       DataContentAcceptanceCommercialCanonical,
	}
	verifier := DataContentFilesystemEvidenceVerifier{
		PublishRoot:  publishRoot,
		EvidenceRoot: evidenceRoot,
	}
	if err := verifier.VerifyDataContentResult(context.Background(), item, result); err != nil {
		t.Fatalf("valid commercial evidence was rejected: %v", err)
	}

	if err := os.WriteFile(
		filepath.Join(canonicalRoot, "page.md"),
		[]byte("# 已漂移\n"),
		0o644,
	); err != nil {
		t.Fatal(err)
	}
	if err := verifier.VerifyDataContentResult(context.Background(), item, result); err == nil ||
		!strings.Contains(err.Error(), "digest mismatch") {
		t.Fatalf("canonical drift was not rejected: %v", err)
	}
}

func TestDataContentFilesystemEvidenceVerifierRejectsEscapingEvidenceRef(t *testing.T) {
	root := t.TempDir()
	publishRoot := filepath.Join(root, "publish")
	evidenceRoot := filepath.Join(root, "evidence")
	if err := os.MkdirAll(publishRoot, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(evidenceRoot, 0o755); err != nil {
		t.Fatal(err)
	}
	err := (DataContentFilesystemEvidenceVerifier{
		PublishRoot:  publishRoot,
		EvidenceRoot: evidenceRoot,
	}).VerifyDataContentResult(
		context.Background(),
		DataContentWorkItem{
			ExecutionID: "20260711--travel-homepage-coverage--cn-test--canary-001",
			Stage:       "publish",
		},
		DataContentExecutionResult{
			ExecutionID:           "20260711--travel-homepage-coverage--cn-test--canary-001",
			CanonicalObjectRef:    "entities/地点/景区/真实地点",
			CanonicalObjectSHA256: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			ObjectTransactionID:   "txn",
			ResultEnvelopeRef:     "../apply_report.json",
			AcceptanceClass:       DataContentAcceptanceCommercialCanonical,
		},
	)
	if err == nil || !strings.Contains(err.Error(), "escapes its root") {
		t.Fatalf("escaping evidence ref was not rejected: %v", err)
	}
}

func TestCountFinalizedDataContentObjectsCountsOnlyReviewedTriples(t *testing.T) {
	evidenceRoot := t.TempDir()
	executionID := "20260727--travel-homepage-coverage--cn-zhejiang--scale-034"
	workPackage := filepath.Join(evidenceRoot, "data", "tasks", executionID)
	writeDataContentObjectFixture(
		t,
		filepath.Join(workPackage, "entities", "地点", "景区", "西湖"),
		"page.md", "manifest.json", "_entity.json",
	)
	writeDataContentObjectFixture(
		t,
		filepath.Join(workPackage, "posts", "article", "西湖春行"),
		"page.md", "manifest.json", "_entity.json",
	)
	writeDataContentObjectFixture(
		t,
		filepath.Join(workPackage, "posts", "article", "未完成"),
		"page.md",
	)
	writeDataContentObjectFixture(
		t,
		filepath.Join(workPackage, "posts", "article", "草稿", "4.draft", "普陀山"),
		"page.md", "manifest.json", "_entity.json",
	)

	finalized, err := CountFinalizedDataContentObjects(evidenceRoot, executionID)

	if err != nil {
		t.Fatal(err)
	}
	if finalized != 2 {
		t.Fatalf("finalized object count=%d want=2", finalized)
	}
}

func TestCountFinalizedDataContentObjectsTreatsAbsentWorkPackageAsZero(t *testing.T) {
	finalized, err := CountFinalizedDataContentObjects(
		t.TempDir(),
		"20260727--travel-homepage-coverage--cn-zhejiang--scale-999",
	)
	if err != nil {
		t.Fatalf("absent work package must not be an error: %v", err)
	}
	if finalized != 0 {
		t.Fatalf("absent work package count=%d want=0", finalized)
	}
}

func TestCountFinalizedDataContentObjectsRequiresEvidenceRoot(t *testing.T) {
	_, err := CountFinalizedDataContentObjects("", "20260727--x--cn-zhejiang--scale-001")
	if err == nil || !strings.Contains(err.Error(), "evidenceRoot") {
		t.Fatalf("empty evidence root was not rejected: %v", err)
	}
}

func writeDataContentObjectFixture(t *testing.T, directory string, files ...string) {
	t.Helper()
	if err := os.MkdirAll(directory, 0o755); err != nil {
		t.Fatal(err)
	}
	for _, name := range files {
		if err := os.WriteFile(filepath.Join(directory, name), []byte(name), 0o644); err != nil {
			t.Fatal(err)
		}
	}
}

func writeDataContentApplyFixture(t *testing.T, path string, payload map[string]string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	data, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, data, 0o644); err != nil {
		t.Fatal(err)
	}
}
