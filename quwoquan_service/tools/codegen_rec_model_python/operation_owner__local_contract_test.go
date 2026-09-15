package main

import (
	"os"
	"path/filepath"
	codegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
	"strings"
	"testing"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
func TestContentCommitOperationOwnerClosure(t *testing.T) {
	view := os.Getenv("QWQ_TEST_CONTRACT_VIEW")
	if view == "" {
		t.Skip("explicit canonical view required")
	}
	source, err := codegen.NewSource(view, validate.ProfileCommercial)
	if err != nil {
		t.Fatal(err)
	}
	out := filepath.Join(t.TempDir(), "receipt.go")
	if err = generateOperationGo(source, "content/content/post", "ReadContentReleaseCommitReceipt", out, false); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(out)
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"type ContentReleaseCommitReceipt struct", "type ContentReleaseFenceChangedPayload struct", "type ContentActiveReleaseFence struct", "type ReadContentReleaseCommitReceiptQuery struct", "operation: ReadContentReleaseCommitReceipt"} {
		if !strings.Contains(string(raw), want) {
			t.Fatal(want)
		}
	}
	if err = generateOperationGo(source, "content/content/post", "ReadContentReleaseCommitReceipt", out, true); err != nil {
		t.Fatal(err)
	}
	if err = generateOperationGo(source, "content/content/post", "MissingOperation", out, false); err == nil {
		t.Fatal("unknown root accepted")
	}
}
