package releaseimport

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strings"
)

// ValidateReplaySourceImportReportOption prevents replay from deriving a
// historical Post identity from the current loader projection.
func ValidateReplaySourceImportReportOption(requireReplay bool, path string) error {
	present := strings.TrimSpace(path) != ""
	if requireReplay && !present {
		return fmt.Errorf("--require-replay requires --replay-source-import-report")
	}
	if !requireReplay && present {
		return fmt.Errorf("--replay-source-import-report requires --require-replay")
	}
	return nil
}

type importedPostReplayReport struct {
	Schema           string                `json:"schema"`
	Status           string                `json:"status"`
	Environment      string                `json:"environment"`
	ReleaseID        string                `json:"releaseId"`
	SourceOwner      string                `json:"sourceOwner"`
	ManifestDigest   string                `json:"manifestDigest"`
	Mode             string                `json:"mode"`
	DeletePolicy     string                `json:"deletePolicy"`
	Counts           map[string]int        `json:"counts"`
	PostBindings     []ImportedPostBinding `json:"postBindings"`
	AuditEvents      []string              `json:"auditEvents"`
	GeneratedAt      string                `json:"generatedAt,omitempty"`
	SourceReportPath string                `json:"sourceReportPath,omitempty"`
}

// LoadImportedPostReplayBindings reads the immutable source import receipt
// used by the repair rail. Those bindings, rather than today's loader-derived
// IDs or sourceHash, own the historical Post identity being proven read-only.
func LoadImportedPostReplayBindings(
	path,
	environment,
	releaseID,
	manifestDigest,
	sourceOwner string,
	desired []PostDoc,
) ([]ImportedPostBinding, error) {
	path = strings.TrimSpace(path)
	if path == "" {
		return nil, fmt.Errorf("GATE_BLOCK: replay source import report is required")
	}
	metadata, err := os.Lstat(path)
	if err != nil {
		return nil, fmt.Errorf("GATE_BLOCK: stat replay source import report: %w", err)
	}
	if metadata.Mode()&os.ModeSymlink != 0 || !metadata.Mode().IsRegular() {
		return nil, fmt.Errorf("GATE_BLOCK: replay source import report must be a regular file")
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("GATE_BLOCK: read replay source import report: %w", err)
	}
	var report importedPostReplayReport
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&report); err != nil {
		return nil, fmt.Errorf("GATE_BLOCK: decode replay source import report: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return nil, fmt.Errorf("GATE_BLOCK: replay source import report contains trailing JSON")
	}
	if report.Schema != "quwoquan.content_import_report" ||
		report.Status != "imported" ||
		report.Environment != strings.TrimSpace(environment) ||
		report.ReleaseID != strings.TrimSpace(releaseID) ||
		report.ManifestDigest != strings.TrimSpace(manifestDigest) ||
		report.SourceOwner != strings.TrimSpace(sourceOwner) ||
		report.Mode != "sync" || report.DeletePolicy != "tombstone" {
		return nil, fmt.Errorf("GATE_BLOCK: replay source import report binding drift")
	}
	postsLoaded := report.Counts["postsLoaded"]
	postsUpserted := report.Counts["postsUpserted"]
	postsRemoved := report.Counts["postsRemoved"]
	if postsLoaded != len(report.PostBindings) || postsUpserted != postsLoaded ||
		postsRemoved <= 0 ||
		report.Counts["outboxEventsAppended"] != postsLoaded+postsRemoved {
		return nil, fmt.Errorf("GATE_BLOCK: replay source import report count drift")
	}
	if err := ValidateImportedPostReplayBindings(desired, report.PostBindings); err != nil {
		return nil, err
	}
	return append([]ImportedPostBinding(nil), report.PostBindings...), nil
}
