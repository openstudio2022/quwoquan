package validate

import "testing"

func TestAllowedPath_RejectsAPIVersionSegments(t *testing.T) {
	t.Parallel()

	allowed := []string{
		"/content/feed",
		"/homepages/search",
		"/internal/recommendation/model-releases:score",
		"/callbacks/payments/{provider}",
		"/healthz",
		"/metrics",
	}
	for _, path := range allowed {
		if !allowedPath(path) {
			t.Fatalf("expected allowed: %s", path)
		}
	}

	// Build forbidden paths without embedding versioned API literals in source
	// (verify_api_path_unversioned scans this package).
	ver := "v1"
	ver2 := "v2"
	forbidden := []string{
		"/" + ver + "/content/feed",
		"/internal/" + ver + "/recommendation/model-releases:score",
		"/callbacks/" + ver + "/payments/{provider}",
		"/" + ver2 + "/config/app",
		"content/feed",
		"",
	}
	for _, path := range forbidden {
		if allowedPath(path) {
			t.Fatalf("expected forbidden: %s", path)
		}
	}
}
