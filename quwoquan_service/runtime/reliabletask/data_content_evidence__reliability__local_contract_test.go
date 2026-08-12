package reliabletask

import (
	"context"
	"encoding/json"
	"fmt"
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

func TestDataContentFilesystemEvidenceVerifierBindsAppliedTransactionAndCanonicalObjectForBothLifecycleStates(
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
	result.AcceptanceClass = DataContentAcceptanceResearchCanonical
	if err := verifier.VerifyDataContentResult(context.Background(), item, result); err != nil {
		t.Fatalf("valid research evidence was rejected: %v", err)
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

func TestCountFinalizedDataContentObjectsUsesCarrierSpecificFinalArtifacts(t *testing.T) {
	tests := []struct {
		carrier    string
		execution  string
		objectPath string
	}{
		{
			carrier:    "homepage",
			execution:  "20260727--travel-homepage-coverage--cn-zhejiang--scale-034",
			objectPath: "entities/地点/景区/西湖",
		},
		{
			carrier:    "article",
			execution:  "20260727--travel-article-coverage--cn-zhejiang--scale-034",
			objectPath: "posts/article/攻略/西湖春行/1",
		},
		{
			carrier:    "image",
			execution:  "20260727--travel-image-coverage--cn-zhejiang--scale-034",
			objectPath: "posts/image/画报/西湖光影/1",
		},
		{
			carrier:    "video",
			execution:  "20260727--travel-video-coverage--cn-zhejiang--scale-034",
			objectPath: "posts/video/体验/西湖晨光/1",
		},
	}
	for _, test := range tests {
		t.Run(test.carrier, func(t *testing.T) {
			evidenceRoot := t.TempDir()
			objectRoot := filepath.Join(
				evidenceRoot,
				"data",
				"tasks",
				test.execution,
				filepath.FromSlash(test.objectPath),
			)
			writeFinalizedDataContentObject(
				t,
				objectRoot,
				test.execution,
				test.carrier,
			)

			finalized, err := CountFinalizedDataContentObjects(
				evidenceRoot,
				test.execution,
				dataContentCarrierJobs(test.execution, test.carrier),
			)

			if err != nil {
				t.Fatal(err)
			}
			if finalized != 1 {
				t.Fatalf("%s finalized object count=%d want=1", test.carrier, finalized)
			}
		})
	}
}

func TestCountFinalizedDataContentObjectsRejectsHomepageTripleAsArticle(t *testing.T) {
	evidenceRoot := t.TempDir()
	executionID := "20260727--travel-article-coverage--cn-zhejiang--scale-035"
	objectRoot := filepath.Join(
		evidenceRoot,
		"data",
		"tasks",
		executionID,
		"posts",
		"article",
		"攻略",
		"伪文章",
		"1",
	)
	writeFinalizedDataContentObject(t, objectRoot, executionID, "homepage")

	finalized, err := CountFinalizedDataContentObjects(
		evidenceRoot,
		executionID,
		dataContentCarrierJobs(executionID, "article"),
	)

	if err != nil {
		t.Fatal(err)
	}
	if finalized != 0 {
		t.Fatalf("homepage triple was miscounted as article: %d", finalized)
	}
}

func TestCountFinalizedDataContentObjectsTreatsAbsentWorkPackageAsZero(t *testing.T) {
	finalized, err := CountFinalizedDataContentObjects(
		t.TempDir(),
		"20260727--travel-homepage-coverage--cn-zhejiang--scale-999",
		dataContentCarrierJobs(
			"20260727--travel-homepage-coverage--cn-zhejiang--scale-999",
			"homepage",
		),
	)
	if err != nil {
		t.Fatalf("absent work package must not be an error: %v", err)
	}
	if finalized != 0 {
		t.Fatalf("absent work package count=%d want=0", finalized)
	}
}

func TestCountFinalizedDataContentObjectsRequiresEvidenceRoot(t *testing.T) {
	executionID := "20260727--travel-image-coverage--cn-zhejiang--scale-001"
	_, err := CountFinalizedDataContentObjects(
		"",
		executionID,
		dataContentCarrierJobs(executionID, "image"),
	)
	if err == nil || !strings.Contains(err.Error(), "evidenceRoot") {
		t.Fatalf("empty evidence root was not rejected: %v", err)
	}
}

func TestResolveDataContentExecutionCreatedAtUsesFrozenExecutionSpec(t *testing.T) {
	evidenceRoot := t.TempDir()
	executionID := "20260727--travel-video-coverage--cn-zhejiang--scale-036"
	specPath := filepath.Join(
		evidenceRoot,
		"data",
		"tasks",
		executionID,
		filepath.FromSlash(dataContentExecutionSpecRef),
	)
	if err := os.MkdirAll(filepath.Dir(specPath), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(
		specPath,
		[]byte("provenance:\n  createdAt: 2026-07-27T01:02:03Z\n"),
		0o644,
	); err != nil {
		t.Fatal(err)
	}

	createdAt, err := ResolveDataContentExecutionCreatedAt(evidenceRoot, executionID)

	if err != nil {
		t.Fatal(err)
	}
	if got := createdAt.Format("2006-01-02T15:04:05Z07:00"); got != "2026-07-27T01:02:03Z" {
		t.Fatalf("execution createdAt=%s", got)
	}
}

func dataContentCarrierJobs(executionID string, carrier string) []DataContentJob {
	return []DataContentJob{{
		ExecutionID: executionID,
		Carrier:     carrier,
	}}
}

func writeFinalizedDataContentObject(
	t *testing.T,
	directory string,
	executionID string,
	carrier string,
) {
	t.Helper()
	if err := os.MkdirAll(directory, 0o755); err != nil {
		t.Fatal(err)
	}
	objectRef := "/entity/地点/景区/西湖"
	if carrier != "homepage" {
		objectRef = "/post/" + carrier + "/fixture"
	}
	writeDataContentJSONFixture(
		t,
		filepath.Join(directory, dataContentReviewAttestationRef),
		map[string]any{
			"executionId":     executionID,
			"objectRef":       objectRef,
			"decision":        "approved",
			"finalizationRef": dataContentFinalizationReportPath,
		},
	)
	switch carrier {
	case "homepage", "article":
		finalRef := "page.md"
		manifest := map[string]any{}
		if carrier == "article" {
			finalRef = "article.md"
			manifest["contentType"] = "article"
		} else if err := os.WriteFile(
			filepath.Join(directory, "_entity.json"),
			[]byte("{}"),
			0o644,
		); err != nil {
			t.Fatal(err)
		}
		writeDataContentJSONFixture(t, filepath.Join(directory, "manifest.json"), manifest)
		body := []byte("# 真实最终产物\n")
		if err := os.WriteFile(filepath.Join(directory, finalRef), body, 0o644); err != nil {
			t.Fatal(err)
		}
		digest, err := dataContentFileSHA256(filepath.Join(directory, finalRef))
		if err != nil {
			t.Fatal(err)
		}
		writeDataContentJSONFixture(
			t,
			filepath.Join(directory, dataContentFinalizationReportRef),
			map[string]any{
				"schema":      "quwoquan_data.finalization",
				"executionId": executionID,
				"finalRef":    finalRef,
				"finalSha256": "sha256:" + fmt.Sprintf("%x", digest),
			},
		)
	case "image":
		assetRef := "assets/cover.jpg"
		if err := os.MkdirAll(filepath.Join(directory, "assets"), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(directory, assetRef), []byte("image"), 0o644); err != nil {
			t.Fatal(err)
		}
		writeDataContentJSONFixture(
			t,
			filepath.Join(directory, "manifest.json"),
			map[string]any{
				"contentType": "image",
				"assets": []map[string]any{{
					"fileName": assetRef,
					"kind":     "image",
				}},
			},
		)
		writeDataContentJSONFixture(
			t,
			filepath.Join(directory, dataContentFinalizationReportRef),
			map[string]any{"schema": "quwoquan_data.finalization"},
		)
	case "video":
		for ref, content := range map[string]string{
			"assets/video.mp4":   "video",
			"assets/poster.webp": "poster",
			"subtitles.vtt":      "WEBVTT",
		} {
			path := filepath.Join(directory, filepath.FromSlash(ref))
			if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
				t.Fatal(err)
			}
		}
		writeDataContentJSONFixture(
			t,
			filepath.Join(directory, "manifest.json"),
			map[string]any{
				"contentType": "video",
				"assets": []map[string]any{{
					"fileName": "assets/video.mp4",
					"kind":     "video",
				}},
			},
		)
		writeDataContentJSONFixture(
			t,
			filepath.Join(directory, dataContentFinalizationReportRef),
			map[string]any{
				"schema":       "quwoquan_data.video_finalization_report",
				"videoRef":     "assets/video.mp4",
				"posterRef":    "assets/poster.webp",
				"subtitlesRef": "subtitles.vtt",
			},
		)
	}
}

func writeDataContentJSONFixture(t *testing.T, path string, payload any) {
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
