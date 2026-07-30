package accountclosure_test

import (
	. "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/infrastructure/accountclosure"
	"strings"
	"testing"
)

func TestHMACSubjectDigestorIsDeterministicAndDoesNotExposeSubject(t *testing.T) {
	digestor, err := NewHMACSubjectDigestor(
		"local-contract-account-closure-key-32-bytes",
	)
	if err != nil {
		t.Fatal(err)
	}

	first, err := digestor.DigestSubject("persona-private-1")
	if err != nil {
		t.Fatal(err)
	}
	replayed, err := digestor.DigestSubject("persona-private-1")
	if err != nil {
		t.Fatal(err)
	}
	other, err := digestor.DigestSubject("persona-private-2")
	if err != nil {
		t.Fatal(err)
	}

	if first != replayed {
		t.Fatalf("same subject digest changed: %q != %q", first, replayed)
	}
	if first == other {
		t.Fatalf("different subjects shared digest %q", first)
	}
	if strings.Contains(first, "persona-private-1") || len(first) != 64 {
		t.Fatalf("subject digest leaked identity or has wrong length: %q", first)
	}
}

func TestHMACSubjectDigestorRejectsWeakConfiguration(t *testing.T) {
	if _, err := NewHMACSubjectDigestor("too-short"); err == nil {
		t.Fatal("weak account-closure HMAC secret must be rejected")
	}
}
