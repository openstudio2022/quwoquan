package ast

import "testing"

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestDerivedResourceIdentityUsesObjectLocalPath(t *testing.T) {
	t.Parallel()

	got, err := DerivedResourceIdentity(
		"search/search/search_index_view/storage.yaml",
		"projection_checkpoints",
	)
	if err != nil {
		t.Fatal(err)
	}
	want := "search/search/search_index_view/projection_checkpoints"
	if got != want {
		t.Fatalf("DerivedResourceIdentity() = %q, want %q", got, want)
	}
	canonical, err := DerivedResourceIdentity(
		"quwoquan_service/services/search-service/contracts/search/search_index_view/storage.yaml",
		"projection_checkpoints",
	)
	if err != nil {
		t.Fatal(err)
	}
	if canonical != "search-service/search/search_index_view/projection_checkpoints" {
		t.Fatalf("canonical repository identity = %q", canonical)
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestStorageResourceRequiredDefaultsTrue(t *testing.T) {
	t.Parallel()

	if !(StorageResource{}).IsRequired() {
		t.Fatal("omitted required must materialize schema default true")
	}
	explicitFalse := false
	if (StorageResource{Required: &explicitFalse}).IsRequired() {
		t.Fatal("explicit required:false was erased")
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestDerivedResourceIdentityRejectsAuthoredOrPhysicalIdentity(t *testing.T) {
	t.Parallel()

	for _, test := range []struct {
		name       string
		sourcePath string
		localName  string
	}{
		{"missing object-local path", "search_index_view/storage.yaml", "projection_checkpoints"},
		{"wrong document", "search/search/search_index_view/object.yaml", "projection_checkpoints"},
		{"path traversal", "search/search/../storage.yaml", "projection_checkpoints"},
		{"uppercase local name", "search/search/search_index_view/storage.yaml", "ProjectionCheckpoints"},
		{"slash local name", "search/search/search_index_view/storage.yaml", "cluster/a"},
	} {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			if _, err := DerivedResourceIdentity(test.sourcePath, test.localName); err == nil {
				t.Fatal("DerivedResourceIdentity accepted non-canonical identity input")
			}
		})
	}
}
