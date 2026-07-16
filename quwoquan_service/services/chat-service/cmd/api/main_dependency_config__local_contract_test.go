package main

import "testing"

func TestRequireInternalServiceBaseURLFailsClosed(t *testing.T) {
	for _, raw := range []string{
		"",
		"user-service:18082",
		"ftp://user-service",
		"http://user:secret@user-service",
		"http://user-service/v1",
		"http://user-service?mode=compat",
	} {
		if _, err := requireInternalServiceBaseURL("USER_SERVICE_BASE_URL", raw); err == nil {
			t.Fatalf("dependency URL %q must be rejected", raw)
		}
	}
}

func TestRequireInternalServiceBaseURLAcceptsExplicitOrigin(t *testing.T) {
	got, err := requireInternalServiceBaseURL(
		"USER_SERVICE_BASE_URL",
		" https://user-service.internal:18082/ ",
	)
	if err != nil {
		t.Fatalf("validate internal origin: %v", err)
	}
	if got != "https://user-service.internal:18082" {
		t.Fatalf("normalized origin=%q", got)
	}
}
