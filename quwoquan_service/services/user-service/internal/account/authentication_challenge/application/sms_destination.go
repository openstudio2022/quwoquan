package authentication_challenge

import (
	"crypto/sha256"
	"encoding/hex"
	"strings"
)

// SMSDestinationHash derives the canonical AuthenticationChallenge destination
// reference from an already-normalized phone credential key.
func SMSDestinationHash(phoneCredentialKey string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(phoneCredentialKey)))
	return hex.EncodeToString(sum[:])
}
