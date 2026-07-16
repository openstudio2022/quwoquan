package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestInitializeContractGraphBundle_BindsAcceptedHash(t *testing.T) {
	graphPath := filepath.Join("..", "..", "generated", "contract_graph.json")
	lockPath := filepath.Join(
		"..",
		"..",
		"..",
		"quwoquan_app",
		"tool",
		"cloud_codegen",
		"contract_graph.lock.json",
	)

	if err := initializeContractGraphBundle(
		filepath.Join("..", "..", "contracts", "metadata"),
		graphPath,
		lockPath,
	); err != nil {
		t.Fatalf("initialize fixed ContractGraph bundle: %v", err)
	}
	if activeContractSHA256 == "" {
		t.Fatal("fixed ContractGraph hash must be exposed to generated manifest")
	}
	if len(activeContractLock.AppExposedOperations) == 0 {
		t.Fatal("accepted App operation exposure cannot be empty")
	}
}

func TestInitializeContractGraphBundle_RejectsHashDrift(t *testing.T) {
	graphPath := filepath.Join("..", "..", "generated", "contract_graph.json")
	graphBytes, err := os.ReadFile(graphPath)
	if err != nil {
		t.Fatalf("read ContractGraph fixture: %v", err)
	}
	lockPath := filepath.Join(
		"..",
		"..",
		"..",
		"quwoquan_app",
		"tool",
		"cloud_codegen",
		"contract_graph.lock.json",
	)
	lockBytes, err := os.ReadFile(lockPath)
	if err != nil {
		t.Fatalf("read lock fixture: %v", err)
	}
	var lock map[string]any
	if err := json.Unmarshal(lockBytes, &lock); err != nil {
		t.Fatalf("decode lock fixture: %v", err)
	}

	temp := t.TempDir()
	tempGraph := filepath.Join(temp, "contract_graph.json")
	tempLock := filepath.Join(temp, "contract_graph.lock.json")
	if err := os.WriteFile(
		tempGraph,
		append(graphBytes, byte('\n')),
		0o600,
	); err != nil {
		t.Fatalf("write drifted graph: %v", err)
	}
	if err := os.WriteFile(tempLock, lockBytes, 0o600); err != nil {
		t.Fatalf("write lock: %v", err)
	}

	err = initializeContractGraphBundle("contracts/metadata", tempGraph, tempLock)
	if err == nil || !strings.Contains(err.Error(), "hash mismatch") {
		t.Fatalf("expected hash mismatch, got %v", err)
	}
}
