package load

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestAllServiceStorageDocumentsUseTheSingleStrictTypedReader(t *testing.T) {
	t.Parallel()

	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("cannot resolve test file path")
	}
	servicesRoot := filepath.Join(filepath.Dir(thisFile), "..", "..", "..", "services")
	count := 0
	err := filepath.WalkDir(servicesRoot, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() || entry.Name() != "storage.yaml" ||
			!strings.Contains(filepath.ToSlash(path), "/contracts/") {
			return nil
		}
		data, readErr := os.ReadFile(path)
		if readErr != nil {
			return readErr
		}
		if _, decodeErr := decodeStorageYAML(data); decodeErr != nil {
			t.Errorf("%s does not match ast.StorageDocument: %v", path, decodeErr)
		}
		count++
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if count < 100 {
		t.Fatalf("strict storage reader covered %d documents, want repository inventory", count)
	}
}

func TestStorageTypedReaderRejectsAliasesAndUnknownNestedFields(t *testing.T) {
	t.Parallel()

	for name, source := range map[string]string{
		"legacy table primary_key": `backend: postgres
role: authoritative
tables:
  records:
    primary_key: id
`,
		"legacy table fk": `backend: postgres
role: authoritative
tables:
  records:
    fk: {column: owner_id, references: owners.id}
`,
		"legacy collection ttl": `backend: mongodb
role: projection
collections:
  records:
    ttl: {field: createdAt, seconds: 60}
`,
		"legacy index ttl": `backend: mongodb
role: projection
collections:
  records:
    indexes:
    - {name: ttl_records, keys: {createdAt: 1}, ttl_seconds: 60}
`,
		"unknown table field": `backend: postgres
role: authoritative
tables:
  records:
    undocumented_magic: true
`,
	} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			if _, err := decodeStorageYAML([]byte(source)); err == nil {
				t.Fatal("strict StorageDocument reader accepted non-canonical field")
			}
		})
	}
}
