package load

import (
	"path/filepath"
	"testing"
)

func TestDebugExternalBinding(t *testing.T) {
	root := filepath.Join("..", "..", "..", "services", "product-ops-service")
	index, err := buildServiceWriteIndex(root)
	if err != nil {
		t.Fatal(err)
	}
	t.Logf("external=%v", index.externalBindings["product_ops_outbox"])
	t.Logf("bindings=%v", index.relationBindings["product_ops_outbox"])
	t.Logf("reads=%v", index.deliveryReads["product_ops_outbox"])
	t.Logf("writes=%v", index.transactionalWrites["product_ops_outbox"])
}
