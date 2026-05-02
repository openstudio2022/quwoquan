package id

import (
	"bytes"
	"strings"
	"testing"
	"time"
)

func TestGenerateAndValidateDefaultPrefixes(t *testing.T) {
	prefixes := []Prefix{
		PrefixAssistantConversation,
		PrefixAssistantTurn,
		PrefixSkillSubscription,
		PrefixDeviceContext,
		PrefixToolUse,
		PrefixAppMessage,
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
		PrefixAssistantConversation,
		WithClock(func() time.Time { return fixedTime }),
		WithEntropy(entropy),
	)
	raw, err := g.Generate()
	if err != nil {
		t.Fatalf("Generate() error = %v", err)
	}
	if raw != "acv_01HRHZ2K3V000G40R40M30E209" {
		t.Fatalf("Generate() = %q", raw)
	}
}

func TestValidateRejectsMalformedIDs(t *testing.T) {
	cases := []string{
		"",
		"acv",
		"bad_01HRJ41Q3V000G40R40M30E209",
		"acv_short",
		"acv_01HRJ41Q3V000G40R40M30E20I",
	}
	for _, raw := range cases {
		t.Run(raw, func(t *testing.T) {
			if IsValid(raw) {
				t.Fatalf("IsValid(%q) = true", raw)
			}
		})
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
