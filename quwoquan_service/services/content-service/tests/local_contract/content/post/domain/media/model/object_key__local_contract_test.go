// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
package model_test

import (
	"testing"

	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
)

// spec_ref: GWT-004
func TestContentAddressedObjectKeyNamespace(t *testing.T) {
	tests := []struct {
		name string
		key  string
		want bool
	}{
		{name: "canonical", key: "media/objects/sha256/aa/bb/source.jpg", want: true},
		{name: "bounded slashes", key: "/media/objects/sha256/aa/bb/source.jpg/", want: true},
		{name: "wrong namespace", key: "media/processed/image/asset/v1/source.jpg"},
		{name: "traversal", key: "media/objects/sha256/aa/../source.jpg"},
		{name: "query suffix", key: "media/objects/sha256/aa/source.jpg?version=1"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if got := mediamodel.IsContentAddressedObjectKey(test.key); got != test.want {
				t.Fatalf("IsContentAddressedObjectKey(%q)=%v, want %v", test.key, got, test.want)
			}
		})
	}
}
