package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"quwoquan_service/internal/metadata/storagecontract"
)

func main() {
	var repoRoot string
	var reportPath string
	flag.StringVar(&repoRoot, "repo-root", "..", "repository root containing quwoquan_service")
	flag.StringVar(&reportPath, "report", "", "optional JSON report path")
	flag.Parse()

	report, err := storagecontract.AuditIndexes(filepath.Clean(repoRoot))
	if err != nil {
		fmt.Fprintf(os.Stderr, "storage-index-governance: %v\n", err)
		os.Exit(2)
	}
	payload, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		fmt.Fprintf(os.Stderr, "storage-index-governance: encode report: %v\n", err)
		os.Exit(2)
	}
	payload = append(payload, '\n')
	if reportPath != "" {
		if err := os.MkdirAll(filepath.Dir(reportPath), 0o755); err != nil {
			fmt.Fprintf(os.Stderr, "storage-index-governance: create report dir: %v\n", err)
			os.Exit(2)
		}
		if err := os.WriteFile(reportPath, payload, 0o600); err != nil {
			fmt.Fprintf(os.Stderr, "storage-index-governance: write report: %v\n", err)
			os.Exit(2)
		}
	}
	_, _ = os.Stdout.Write(payload)
	if len(report.Issues) > 0 {
		os.Exit(1)
	}
}
