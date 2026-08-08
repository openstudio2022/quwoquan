package storagecontract

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestStorageConsumersUseTheCanonicalDecoder(t *testing.T) {
	t.Parallel()
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test file")
	}
	serviceRoot := filepath.Clean(filepath.Join(filepath.Dir(thisFile), "..", "..", ".."))
	consumers := map[string]string{
		"internal/metadata/load/load.go":                 "storagecontract.LoadOptional(",
		"internal/metadata/load/business_object_maps.go": "storagecontract.DecodeJSON(",
		"internal/metadata/load/publication_evidence.go": "storagecontract.LoadOptional(",
		"internal/metadata/validate/storage.go":          "storagecontract.LoadOptional(",
		"tools/codegen_storage/generation_plan.go":       "storagecontract.DecodeYAML(",
		"tools/codegen_storage/main.go":                  "storagecontract.DecodeJSON(",
		"tools/storage_contract_view/main.go":            "storagecontract.DecodeYAML(",
		"tools/verify_metadata/main.go":                  "storagecontract.DecodeYAML(",
	}
	for relative, required := range consumers {
		relative, required := relative, required
		t.Run(relative, func(t *testing.T) {
			t.Parallel()
			data, err := os.ReadFile(filepath.Join(serviceRoot, filepath.FromSlash(relative)))
			if err != nil {
				t.Fatal(err)
			}
			source := string(data)
			if !strings.Contains(source, required) {
				t.Fatalf("%s must call %s", relative, required)
			}
			for _, retired := range []string{
				"type StorageYAML struct", "decodeStorageYAML(", "decodeStorageJSON(",
				"loadOptionalStorageDocument(",
			} {
				if strings.Contains(source, retired) {
					t.Fatalf("%s retains retired storage decoder %q", relative, retired)
				}
			}
		})
	}
}
