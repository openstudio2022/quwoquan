package linktemplates

import "testing"

func TestUserWebPathUsesMetadataOwnedTemplateAndEscapesOneSegment(t *testing.T) {
	t.Parallel()

	if got, want := UserWebPath(" alice/bob "), "/u/alice%2Fbob"; got != want {
		t.Fatalf("UserWebPath() = %q, want %q", got, want)
	}
}
