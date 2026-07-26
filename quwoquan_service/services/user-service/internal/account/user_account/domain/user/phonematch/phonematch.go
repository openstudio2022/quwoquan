// Package phonematch is the single source of truth for the deterministic
// phone-number canonicalization + hashing used by contact discovery.
//
// Contact discovery requires the client and the server to derive identical
// hashes for the same human phone number. The "salt" below is therefore a
// shared application-wide namespacing constant (it ships inside the client
// binary and is NOT a secret). The Dart client mirrors this exact algorithm in
// `lib/ui/user/services/contact_hash_service.dart`; the two MUST stay in sync
// (locked by a shared test vector in both languages).
package phonematch

import (
	"crypto/sha256"
	"encoding/hex"
	"strings"
)

// Salt namespaces the hash so the same phone hashed for an unrelated purpose
// never collides with a contact-discovery hash. Bump the version suffix only
// together with the Dart client constant.
const Salt = "qwq.contact.v1"

// Canonicalize normalizes a raw phone string toward an E.164-ish form so that
// the same number stored in different shapes ("138 1234 5678", "+8613...",
// "13...") collapses to one deterministic value on both client and server.
//
// CN mobiles (11 digits starting with 1) are promoted to +86. Numbers that
// already carry an explicit "+" or country code are kept as "+<digits>". The
// algorithm is intentionally symmetric: as long as client and server feed the
// same underlying number, they produce the same canonical string.
func Canonicalize(phone string) string {
	trimmed := strings.TrimSpace(phone)
	if trimmed == "" {
		return ""
	}
	hasPlus := strings.HasPrefix(trimmed, "+")
	digits := onlyDigits(trimmed)
	if digits == "" {
		return ""
	}
	switch {
	case hasPlus:
		return "+" + digits
	case len(digits) == 11 && digits[0] == '1':
		return "+86" + digits
	case len(digits) == 13 && strings.HasPrefix(digits, "86"):
		return "+" + digits
	case len(digits) == 14 && strings.HasPrefix(digits, "086"):
		return "+" + digits[1:]
	default:
		return "+" + digits
	}
}

// Hash returns the hex SHA-256 of "<Salt>:<canonical>" or "" for empty input.
func Hash(phone string) string {
	canon := Canonicalize(phone)
	if canon == "" {
		return ""
	}
	sum := sha256.Sum256([]byte(Salt + ":" + canon))
	return hex.EncodeToString(sum[:])
}

func onlyDigits(s string) string {
	var b strings.Builder
	for _, r := range s {
		if r >= '0' && r <= '9' {
			b.WriteRune(r)
		}
	}
	return b.String()
}
