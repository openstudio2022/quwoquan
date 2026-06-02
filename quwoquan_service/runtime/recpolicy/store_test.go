package recpolicy

import (
	"os"
	"path/filepath"
	"testing"
)

func TestStore_BaselineFallback(t *testing.T) {
	s := NewStore(nil)
	if s.Current() == nil {
		t.Fatal("Current must never be nil")
	}
	if s.Current().PolicyVersion != BaselinePolicyVersion {
		t.Fatalf("seeded version = %q, want baseline %q", s.Current().PolicyVersion, BaselinePolicyVersion)
	}
	if s.EffectiveHash() == "" {
		t.Fatal("effective hash should be set after seed")
	}
}

func TestStore_ApplyHotSwap(t *testing.T) {
	s := NewStoreFromBaseline()
	before := s.EffectiveHash()

	hash, err := s.Apply([]byte(testPolicyYAML))
	if err != nil {
		t.Fatalf("apply valid policy: %v", err)
	}
	if hash == before {
		t.Fatal("hash should change after applying a different policy")
	}
	if s.Current().PolicyVersion != "test-v1" {
		t.Fatalf("current version = %q, want test-v1", s.Current().PolicyVersion)
	}
}

func TestStore_ApplyInvalidKeepsLastGood(t *testing.T) {
	s := NewStoreFromBaseline()
	good, err := s.Apply([]byte(testPolicyYAML))
	if err != nil {
		t.Fatalf("seed good: %v", err)
	}

	// A structurally invalid candidate (defaultPreset not in weightPresets)
	// must be rejected and the last-good policy retained.
	bad := `
version: 1
policyVersion: broken
defaultPreset: missing
weightPresets:
  control: { tagRelevance: 1.0 }
scorer:
  freshnessHalfLifeHours: 24.0
  maxAuthorPerFeed: 3
  exploreFraction: 0.1
`
	hash, err := s.Apply([]byte(bad))
	if err == nil {
		t.Fatal("expected validation error for bad policy")
	}
	if hash != good {
		t.Fatalf("hash changed on rejected apply: %q != %q", hash, good)
	}
	if s.Current().PolicyVersion != "test-v1" {
		t.Fatalf("last-good not retained: version = %q", s.Current().PolicyVersion)
	}
}

func TestStore_ApplyFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "policy.yaml")
	if err := os.WriteFile(path, []byte(testPolicyYAML), 0o644); err != nil {
		t.Fatalf("write: %v", err)
	}
	s := NewStoreFromBaseline()
	if _, err := s.ApplyFile(path); err != nil {
		t.Fatalf("apply file: %v", err)
	}
	if s.Current().PolicyVersion != "test-v1" {
		t.Fatalf("version = %q", s.Current().PolicyVersion)
	}

	// Missing file keeps last-good.
	if _, err := s.ApplyFile(filepath.Join(dir, "nope.yaml")); err == nil {
		t.Fatal("expected error for missing file")
	}
	if s.Current().PolicyVersion != "test-v1" {
		t.Fatal("last-good not retained after missing file")
	}
}
