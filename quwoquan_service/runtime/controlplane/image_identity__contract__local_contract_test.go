package controlplane

import "testing"

func TestValidateImageIdentityRequiresOneImmutableToken(t *testing.T) {
	t.Parallel()

	for _, identity := range []string{
		"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		"release-20260730-1",
	} {
		if err := ValidateImageIdentity(identity); err != nil {
			t.Fatalf("expected canonical image identity %q to pass: %v", identity, err)
		}
	}

	for _, identity := range []string{
		"",
		"latest",
		"down",
		"package-required",
		"source-provenance-required",
		"two identities",
	} {
		if err := ValidateImageIdentity(identity); err == nil {
			t.Fatalf("expected non-canonical image identity %q to fail", identity)
		}
	}
}
