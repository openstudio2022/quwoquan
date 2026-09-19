package id

import (
	"bytes"
	"errors"
	"strings"
	"testing"
	"time"
)

func TestGenerateAndValidateDefaultPrefixes(t *testing.T) {
	prefixes := []Prefix{
		PrefixAssistantSession,
		PrefixAssistantTurn,
		PrefixAssistantPreference,
		PrefixSkillSubscription,
		PrefixDeviceContext,
		PrefixToolUse,
		PrefixAppMessage,
		PrefixNotificationDeliveryJob,
	}
	for _, prefix := range prefixes {
		t.Run(string(prefix), func(t *testing.T) {
			g := MustNewGenerator(prefix)
			raw, err := g.Generate()
			if err != nil {
				t.Fatalf("Generate() error = %v", err)
			}
			if !strings.HasPrefix(raw, string(prefix)) {
				t.Fatalf("id %q does not start with %q", raw, prefix)
			}
			if len(raw) != len(prefix)+ulidLength {
				t.Fatalf("id length = %d, want %d", len(raw), len(prefix)+ulidLength)
			}
			if err := Validate(raw); err != nil {
				t.Fatalf("Validate(%q) error = %v", raw, err)
			}
		})
	}
}

func TestGenerateWithDeterministicEntropy(t *testing.T) {
	fixedTime := time.UnixMilli(1710000000123).UTC()
	entropy := bytes.NewReader([]byte{0, 1, 2, 3, 4, 5, 6, 7, 8, 9})
	g := MustNewGenerator(
		PrefixAssistantSession,
		WithClock(func() time.Time { return fixedTime }),
		WithEntropy(entropy),
	)
	raw, err := g.Generate()
	if err != nil {
		t.Fatalf("Generate() error = %v", err)
	}
	if raw != "asn_01HRHZ2K3V000G40R40M30E209" {
		t.Fatalf("Generate() = %q", raw)
	}
}

func TestValidateRejectsMalformedIDs(t *testing.T) {
	cases := []string{
		"",
		"asn",
		"bad_01HRJ41Q3V000G40R40M30E209",
		"asn_short",
		"asn_01HRJ41Q3V000G40R40M30E20I",
		"asn_81HRJ41Q3V000G40R40M30E209",
		"asn_Z1HRJ41Q3V000G40R40M30E209",
	}
	for _, raw := range cases {
		t.Run(raw, func(t *testing.T) {
			if IsValid(raw) {
				t.Fatalf("IsValid(%q) = true", raw)
			}
		})
	}
}

// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-004
func TestGenerateAtRejectsUnencodableTimestamps(t *testing.T) {
	cases := map[string]time.Time{
		"before unix epoch":   time.UnixMilli(-1).UTC(),
		"beyond 48 bit range": time.UnixMilli(maxTimestampMilliseconds).UTC(),
	}
	for name, instant := range cases {
		t.Run(name, func(t *testing.T) {
			g := MustNewGenerator(PrefixAssistantSession, WithClock(func() time.Time { return instant }))
			if _, err := g.Generate(); !errors.Is(err, ErrTimestampOutOfRange) {
				t.Fatalf("Generate() error = %v, want ErrTimestampOutOfRange", err)
			}
		})
	}

	last := time.UnixMilli(maxTimestampMilliseconds - 1).UTC()
	g := MustNewGenerator(PrefixAssistantSession, WithClock(func() time.Time { return last }))
	if _, err := g.Generate(); err != nil {
		t.Fatalf("last encodable millisecond must stay valid, got %v", err)
	}
}

// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-004
func TestGenerateSurfacesEntropyFailureWithoutWeakFallback(t *testing.T) {
	g := MustNewGenerator(PrefixAssistantSession, WithEntropy(bytes.NewReader([]byte{1, 2, 3})))
	raw, err := g.Generate()
	if !errors.Is(err, ErrEntropyUnavailable) {
		t.Fatalf("Generate() error = %v, want ErrEntropyUnavailable", err)
	}
	if raw != "" {
		t.Fatalf("failed allocation must not return an id, got %q", raw)
	}
}

func TestRegistryRejectsConflictingOwners(t *testing.T) {
	reg := NewRegistry()
	if err := reg.Register("abc_", "first"); err != nil {
		t.Fatalf("Register first error = %v", err)
	}
	if err := reg.Register("abc_", "first"); err != nil {
		t.Fatalf("Register same owner error = %v", err)
	}
	if err := reg.Register("abc_", "second"); err == nil {
		t.Fatal("Register conflicting owner error = nil")
	}
}
