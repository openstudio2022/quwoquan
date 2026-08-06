package graph

import (
	"strings"
	"testing"

	metadataast "quwoquan_service/internal/metadata/ast"
)

func TestProvenPythonOutboxWithoutDeliveryIsStructuralGap(t *testing.T) {
	t.Parallel()

	evidence := metadataast.ObjectReadinessEvidence{
		PublicationStores:    []string{"rec_model_release_outbox"},
		DeliveryStores:       []string{"rec_model_release_outbox"},
		PythonImplementation: true,
		Service: metadataast.ServiceStructureEvidence{
			Outbox: []metadataast.StorageEvidence{{
				Storage: "rec_model_release_outbox",
				Artifact: metadataast.EvidenceArtifact{
					Path:   "services/recommendation-service/internal/model/store.py",
					SHA256: strings.Repeat("a", 64),
				},
			}},
		},
	}
	missing := map[string]struct{}{}
	if requirePublicationSeam(evidence, missing) {
		t.Fatal("outbox 没有投递实现时不得 ready")
	}
	if _, ok := missing["implementation.publication_delivery"]; !ok {
		t.Fatalf("missing=%v, want implementation.publication_delivery", missing)
	}
	if _, ok := missing["blindspot.python_store_invisible"]; ok {
		t.Fatalf("已证明 Python 事务写入后不得把投递缺失继续归为 scanner blindspot: %v", missing)
	}
}

func TestUnprovenPythonOutboxRemainsScannerBlindspot(t *testing.T) {
	t.Parallel()

	evidence := metadataast.ObjectReadinessEvidence{
		PublicationStores:    []string{"unresolved_python_outbox"},
		DeliveryStores:       []string{"unresolved_python_outbox"},
		PythonImplementation: true,
	}
	missing := map[string]struct{}{}
	if requirePublicationSeam(evidence, missing) {
		t.Fatal("未证明事务写入时不得 ready")
	}
	if _, ok := missing["blindspot.python_store_invisible"]; !ok {
		t.Fatalf("missing=%v, want blindspot.python_store_invisible", missing)
	}
}
