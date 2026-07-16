package main

import (
	"path/filepath"
	"sync"
	"testing"
)

var (
	testContractGraphOnce sync.Once
	testContractGraphErr  error
)

func initializeTestContractGraph(t *testing.T) string {
	t.Helper()
	metadataDir := filepath.Join("..", "..", "contracts", "metadata")
	testContractGraphOnce.Do(func() {
		testContractGraphErr = initializeContractGraph(metadataDir)
	})
	if testContractGraphErr != nil {
		t.Fatalf("initialize ContractGraph: %v", testContractGraphErr)
	}
	return metadataDir
}
