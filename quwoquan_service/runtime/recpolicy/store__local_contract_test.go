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
	if s.EffectiveHash() == "" {
		t.Fatal("effective hash should be set after seed")
	}
	if s.Current().effectiveHash != s.EffectiveHash() {
		t.Fatalf("policy digest %q != store digest %q", s.Current().effectiveHash, s.EffectiveHash())
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
	if s.Current().effectiveHash != hash {
		t.Fatalf("current policy digest = %q, want %q", s.Current().effectiveHash, hash)
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
	if s.Current().effectiveHash != good {
		t.Fatalf("last-good digest not retained: %q != %q", s.Current().effectiveHash, good)
	}
}

func TestStore_ApplyFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "policy.yaml")
	if err := os.WriteFile(path, []byte(testPolicyYAML), 0o644); err != nil {
		t.Fatalf("write: %v", err)
	}
	s := NewStoreFromBaseline()
	hash, err := s.ApplyFile(path)
	if err != nil {
		t.Fatalf("apply file: %v", err)
	}
	if s.Current().effectiveHash != hash {
		t.Fatalf("policy digest = %q, want %q", s.Current().effectiveHash, hash)
	}

	// Missing file keeps last-good.
	if _, err := s.ApplyFile(filepath.Join(dir, "nope.yaml")); err == nil {
		t.Fatal("expected error for missing file")
	}
	if s.Current().effectiveHash != hash {
		t.Fatal("last-good not retained after missing file")
	}
}
