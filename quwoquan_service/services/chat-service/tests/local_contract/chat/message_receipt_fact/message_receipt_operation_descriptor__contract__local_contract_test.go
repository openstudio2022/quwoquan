package local_contract

import (
	"testing"

	"quwoquan_service/generated/operationsecurity"
)

func TestMessageReceiptFactOwnsItsCommercialOperationDescriptor(t *testing.T) {
	t.Parallel()

	const operationID = "chat.message_receipt_fact.GetReceipts"
	for _, descriptor := range operationsecurity.ForDomain("chat") {
		if descriptor.CanonicalOperationID != operationID {
			continue
		}
		if descriptor.CommercialStatus != "ready" || descriptor.AuthMode != "required" {
			t.Fatalf(
				"%s status/auth = %q/%q, want ready/required",
				operationID,
				descriptor.CommercialStatus,
				descriptor.AuthMode,
			)
		}
		return
	}
	t.Fatalf("generated operation security descriptor missing %s", operationID)
}
