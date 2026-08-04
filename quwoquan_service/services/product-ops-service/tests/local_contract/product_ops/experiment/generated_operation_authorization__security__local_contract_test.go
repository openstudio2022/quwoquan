// spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001
package local_contract

import (
	"net/http"
	"slices"
	"testing"

	generatedcontrolplane "quwoquan_service/generated/control_plane"
)

func TestProductOpsGeneratedAuthorizationIncludesCreateExperiment(t *testing.T) {
	const operationID = "ops.experiment.CreateExperiment"
	for _, descriptor := range generatedcontrolplane.ProductOperationSecurityDescriptors {
		if descriptor.CanonicalOperationID != operationID {
			continue
		}
		if descriptor.Method != http.MethodPost ||
			descriptor.PathTemplate != "/control-plane/product/experiments" ||
			descriptor.Principal != "operator" ||
			!slices.Contains(descriptor.Scopes, "ops.experiment.write") ||
			descriptor.CommercialStatus != "ready" {
			t.Fatalf("unexpected CreateExperiment authorization: %+v", descriptor)
		}
		return
	}
	t.Fatalf("%s is absent from Product Ops generated authorization", operationID)
}
