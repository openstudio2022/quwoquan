// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-016
package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestMediaAssetRetiresResearchMembershipContractAndIndex(t *testing.T) {
	_, sourcePath, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source path")
	}
	serviceRoot := filepath.Clean(filepath.Join(filepath.Dir(sourcePath), "../../../.."))
	for _, path := range []string{
		"contracts/media/media_asset/fields.yaml",
		"contracts/media/media_asset/object.yaml",
		"contracts/media/media_asset/storage.yaml",
		"internal/media/media_asset/infrastructure/persistence/mongo_indexes.go",
	} {
		t.Run(path, func(t *testing.T) {
			data, err := os.ReadFile(filepath.Join(serviceRoot, path))
			if err != nil {
				t.Fatal(err)
			}
			for _, retired := range []string{"sourceReleaseIds", "idx_media_assets_source_release"} {
				if strings.Contains(string(data), retired) {
					t.Errorf("retired research membership %q remains in %s", retired, path)
				}
			}
			// 单值 release 诊断事实仍由 importer 使用，不随 research 权限退役。
			if strings.HasSuffix(path, "fields.yaml") || strings.HasSuffix(path, "object.yaml") {
				if !strings.Contains(string(data), "sourceReleaseId") {
					t.Errorf("release diagnostic sourceReleaseId must remain in %s", path)
				}
			}
		})
	}
}
