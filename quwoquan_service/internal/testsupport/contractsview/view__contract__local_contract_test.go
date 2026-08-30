package contractsview_test

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/testsupport/contractsview"
)

const provenanceFilename = ".contract-view-provenance"

// 版本标识是 format 而非独立的 schemaVersion：生产加载器
// internal/metadata/load/contract_view_provenance.go 对该文档启用
// DisallowUnknownFields，多写一个版本字段会让加载 fail closed。
type provenanceDocument struct {
	Format string `json:"format"`
	Files  []struct {
		Path        string   `json:"path"`
		SHA256      string   `json:"sha256"`
		SourcePaths []string `json:"sourcePaths"`
	} `json:"files"`
}

func TestBuildCreatesByteSnapshotWithCanonicalProvenance(t *testing.T) {
	metadataDir := contractsview.Build(t)
	payload, err := os.ReadFile(filepath.Join(metadataDir, provenanceFilename))
	if err != nil {
		t.Fatalf("read contract view provenance: %v", err)
	}
	var document provenanceDocument
	if err := json.Unmarshal(payload, &document); err != nil {
		t.Fatalf("decode contract view provenance: %v", err)
	}
	if document.Format != "contract-view-provenance" || len(document.Files) == 0 {
		t.Fatalf("contract view provenance is incomplete: %+v", document)
	}

	operationsChecked := false
	for _, file := range document.Files {
		absolute := filepath.Join(metadataDir, filepath.FromSlash(file.Path))
		info, err := os.Lstat(absolute)
		if err != nil {
			t.Fatalf("inspect snapshot %s: %v", file.Path, err)
		}
		if !info.Mode().IsRegular() {
			t.Fatalf("snapshot %s mode=%s, want regular byte snapshot", file.Path, info.Mode())
		}
		content, err := os.ReadFile(absolute)
		if err != nil {
			t.Fatalf("read snapshot %s: %v", file.Path, err)
		}
		digest := sha256.Sum256(content)
		if hex.EncodeToString(digest[:]) != file.SHA256 {
			t.Fatalf("snapshot %s digest drifted from provenance", file.Path)
		}
		if strings.HasSuffix(file.Path, "/operations.yaml") && !operationsChecked {
			if len(file.SourcePaths) != 1 ||
				!strings.HasPrefix(file.SourcePaths[0], "quwoquan_service/services/") ||
				!strings.Contains(file.SourcePaths[0], "/contracts/") ||
				!strings.HasSuffix(file.SourcePaths[0], "/operations.yaml") {
				t.Fatalf("operations provenance is not canonical object-local source: %+v", file)
			}
			operationsChecked = true
		}
	}
	if !operationsChecked {
		t.Fatal("contract view provenance has no object-local operations source")
	}

	secondView := contractsview.Build(t)
	firstFile := document.Files[0]
	firstPath := filepath.Join(metadataDir, filepath.FromSlash(firstFile.Path))
	secondPath := filepath.Join(secondView, filepath.FromSlash(firstFile.Path))
	secondBefore, err := os.ReadFile(secondPath)
	if err != nil {
		t.Fatalf("read second test snapshot %s: %v", firstFile.Path, err)
	}
	if err := os.WriteFile(firstPath, []byte("test-local mutation\n"), 0o644); err != nil {
		t.Fatalf("mutate first test snapshot: %v", err)
	}
	secondAfter, err := os.ReadFile(secondPath)
	if err != nil {
		t.Fatalf("reread second test snapshot %s: %v", firstFile.Path, err)
	}
	if !bytes.Equal(secondBefore, secondAfter) {
		t.Fatal("test-local view mutation crossed into a sibling byte snapshot")
	}
}
