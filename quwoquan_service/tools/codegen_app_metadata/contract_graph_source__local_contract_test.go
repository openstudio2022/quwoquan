package main

import (
	"encoding/json"
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

func TestAppContractLockDecodesOperationConsistencyStrictly(t *testing.T) {
	payload := []byte(`{
  "appExposedOperations": [{
    "canonicalOperationId": "search.search_index_view.SearchPage",
    "consistency": {
      "source": "projection",
      "freshness": "bounded",
      "maxStalenessSeconds": 15,
      "staleResult": "with_watermark"
    }
  }]
}`)
	var lock appContractLock
	if err := json.Unmarshal(payload, &lock); err != nil {
		t.Fatal(err)
	}
	if len(lock.AppExposedOperations) != 1 || lock.AppExposedOperations[0].Consistency == nil {
		t.Fatalf("operation consistency missing from decoded lock: %+v", lock.AppExposedOperations)
	}
	consistency := lock.AppExposedOperations[0].Consistency
	if consistency.Source != "projection" || consistency.Freshness != "bounded" ||
		consistency.MaxStalenessSeconds != 15 || consistency.StaleResult != "with_watermark" {
		t.Fatalf("decoded operation consistency = %+v", consistency)
	}
}
