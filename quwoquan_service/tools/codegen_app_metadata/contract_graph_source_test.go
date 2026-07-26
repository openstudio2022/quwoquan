package main

import (
	"testing"

	"quwoquan_service/internal/testsupport/contractsview"
)

func initializeTestContractGraph(t *testing.T) string {
	t.Helper()
	metadataDir := contractsview.Build(t)
	if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
		t.Fatalf("initialize ContractGraph: %v", err)
	}
	return metadataDir
}
