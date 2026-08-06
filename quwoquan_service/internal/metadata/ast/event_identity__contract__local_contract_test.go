package ast

import "testing"

func TestCanonicalEventRefRequiresObjectQualifiedPascalCaseIdentity(t *testing.T) {
	t.Parallel()

	if got := CanonicalEventRef("content.post", "PostPublished"); got != "content.post.PostPublished" {
		t.Fatalf("CanonicalEventRef() = %q", got)
	}
	for _, valid := range []string{
		"content.post.PostPublished",
		"ops.premium_pool_entry.PremiumPoolEntryUpserted",
	} {
		if !IsCanonicalEventRef(valid) {
			t.Fatalf("canonical event ref rejected: %s", valid)
		}
	}
	for _, invalid := range []string{
		"content.PostPublished",
		"content.post.postPublished",
		"content-service.post.PostPublished",
		"events.content.post_lifecycle",
	} {
		if IsCanonicalEventRef(invalid) {
			t.Fatalf("non-canonical event ref accepted: %s", invalid)
		}
	}
}
