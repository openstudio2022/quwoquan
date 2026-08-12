// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-005
package local_contract

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestContentOwnerMountsOnlyTheRuntimeOperationBoundary(t *testing.T) {
	t.Parallel()
	source, err := os.ReadFile(
		filepath.Join(contentServiceRoot(t), "cmd", "api", "main_http_runtime.go"),
	)
	if err != nil {
		t.Fatal(err)
	}
	text := string(source)
	if !strings.Contains(text, "rtauth.EnforceRuntimeOperationContract(") {
		t.Fatal("content owner does not mount the generated runtime operation contract")
	}
	if strings.Contains(text, "rtauth.RequireGeneratedOperationAuthorization(") {
		t.Fatal("content owner must not duplicate the api-edge commercial boundary")
	}
}
