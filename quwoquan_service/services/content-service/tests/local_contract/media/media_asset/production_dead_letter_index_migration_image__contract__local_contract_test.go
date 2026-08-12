// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestProductionImagePackagesMediaDeadLetterIndexMigration(t *testing.T) {
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve local contract source path")
	}
	serviceRoot := filepath.Clean(filepath.Join(filepath.Dir(file), "../../../.."))
	dockerfile, err := os.ReadFile(filepath.Join(serviceRoot, "build/Dockerfile"))
	if err != nil {
		t.Fatalf("read production Dockerfile: %v", err)
	}
	content := string(dockerfile)
	for _, required := range []string{
		"go build ${GO_BUILD_FLAGS} -o /migrate-media-processing-dead-letter-indexes ./services/content-service/cmd/migrate-media-processing-dead-letter-indexes/",
		"COPY --from=builder /migrate-media-processing-dead-letter-indexes /usr/local/bin/migrate-media-processing-dead-letter-indexes",
	} {
		if !strings.Contains(content, required) {
			t.Fatalf("production image must package MediaAsset storage migration %q", required)
		}
	}
}
