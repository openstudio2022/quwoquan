package objectstorage_test

import (
	"strings"
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/objectstorage"
)

func TestLoadBindingFailsClosedWithoutMaterials(t *testing.T) {
	_, err := LoadBinding("gamma", runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{}})
	if err == nil || !strings.Contains(err.Error(), "endpoint material is unavailable") {
		t.Fatalf("missing materials must fail closed: %v", err)
	}
}

func TestLoadBindingMaterializesMinIOLocalSubstitute(t *testing.T) {
	binding, err := LoadBinding(
		"gamma",
		runtimeconfig.MapRuntimeConfigProvider{
			Values: map[string]string{
				"CONTENT_OSS_ENDPOINT":          "https://gamma-upload.quwoquan-env.test:19130",
				"CONTENT_OSS_ACCESS_KEY_ID":     "fixture-access",
				"CONTENT_OSS_ACCESS_KEY_SECRET": "fixture-secret",
				"CONTENT_CDN_SIGN_KEY":          "fixture-cdn-sign-key",
			},
		},
	)
	if err != nil {
		t.Fatalf("LoadBinding() error = %v", err)
	}
	if binding.AdapterID != MinIOAdapterID {
		t.Fatalf("AdapterID = %q, want %q", binding.AdapterID, MinIOAdapterID)
	}
	if binding.AccessKeyID != "fixture-access" {
		t.Fatalf("AccessKeyID = %q", binding.AccessKeyID)
	}
}
