package support

import (
	"crypto/sha256"
	"fmt"
)

// CanonicalTestSHA256 derives a syntactically and semantically bound digest
// from the fixture payload instead of accepting a named placeholder.
func CanonicalTestSHA256(payload string) string {
	return fmt.Sprintf("sha256:%x", sha256.Sum256([]byte(payload)))
}
