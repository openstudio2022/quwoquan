package local_contract

import (
	"testing"

	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/phonematch"
)

// lockedVector is the canonical contact-discovery hash for 13800138000.
// The Dart client mirror (contact_hash_service_test.dart) asserts the SAME
// value so client and server can never silently diverge.
const lockedVector = "ec1a7eb3a4a2d69b978580e3d74fc3677cb2b4ebc2e1a58be568310147539484"

func TestHashLockedVector(t *testing.T) {
	if got := phonematch.Hash("13800138000"); got != lockedVector {
		t.Fatalf("locked hash drift: got %s want %s", got, lockedVector)
	}
}

func TestCanonicalizeCollapsesEquivalentForms(t *testing.T) {
	forms := []string{
		"13800138000",
		"+8613800138000",
		"86 138 0013 8000",
		"138-0013-8000",
		"(138) 0013 8000",
	}
	for _, f := range forms {
		if got := phonematch.Canonicalize(f); got != "+8613800138000" {
			t.Fatalf("canonicalize(%q) = %q, want +8613800138000", f, got)
		}
		if got := phonematch.Hash(f); got != lockedVector {
			t.Fatalf("hash(%q) = %q, want locked vector", f, got)
		}
	}
}

func TestEmptyInputs(t *testing.T) {
	for _, f := range []string{"", "   ", "()", "+"} {
		if got := phonematch.Canonicalize(f); got != "" {
			t.Fatalf("canonicalize(%q) = %q, want empty", f, got)
		}
		if got := phonematch.Hash(f); got != "" {
			t.Fatalf("hash(%q) = %q, want empty", f, got)
		}
	}
}
