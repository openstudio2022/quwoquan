package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestDevicePushEndpointKindHasOneSharedOwner(t *testing.T) {
	t.Parallel()

	root := repositoryRoot(t)
	shared := readContract(t, filepath.Join(
		root,
		"quwoquan_service/contracts/metadata/_shared/types.yaml",
	))
	if strings.Count(shared, "DevicePushEndpointKind:") != 1 ||
		!strings.Contains(shared, "DevicePushEndpointKind: [apns_voip, fcm]") {
		t.Fatal("DevicePushEndpointKind must have one shared canonical definition")
	}

	userFields := readContract(t, filepath.Join(
		root,
		"quwoquan_service/services/user-service/contracts/account/device_registration/fields.yaml",
	))
	if strings.Contains(userFields, "  DevicePushEndpointKind:") {
		t.Fatal("user object retains a duplicate DevicePushEndpointKind enum owner")
	}
	if !strings.Contains(userFields, "enum_ref: DevicePushEndpointKind") {
		t.Fatal("user device registration no longer references the shared enum")
	}

	integrationFields := readContract(t, filepath.Join(
		root,
		"quwoquan_service/services/integration-service/contracts/external_integration/push_delivery/fields.yaml",
	))
	if !strings.Contains(integrationFields, "enum_ref: DevicePushEndpointKind") {
		t.Fatal("integration push invalidation no longer references the shared enum")
	}
}

func repositoryRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve contract test path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", "..", "..", "..", ".."))
}

func readContract(t *testing.T, path string) string {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return string(raw)
}
