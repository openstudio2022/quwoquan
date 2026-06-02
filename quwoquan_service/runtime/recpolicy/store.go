package recpolicy

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"sync/atomic"
)

// Store holds the live recommendation policy behind an atomic.Pointer so the
// scoring hot-path reads it lock-free. Apply performs validate-before-swap:
// an invalid candidate is rejected and the last-good policy is retained, so a
// bad YAML edit can never zero out scoring or crash the engine.
type Store struct {
	ptr  atomic.Pointer[RecPolicy]
	hash atomic.Pointer[string]
}

// NewStore seeds the store. A nil initial policy falls back to the codegen
// Baseline so Current never returns nil.
func NewStore(initial *RecPolicy) *Store {
	s := &Store{}
	if initial == nil {
		initial = Baseline()
	}
	s.swap(initial)
	return s
}

// NewStoreFromBaseline seeds the store with the compile-time baseline snapshot.
func NewStoreFromBaseline() *Store {
	return NewStore(Baseline())
}

func (s *Store) swap(p *RecPolicy) {
	s.ptr.Store(p)
	h := policyHash(p)
	s.hash.Store(&h)
}

// Current returns the live policy. Never nil (falls back to Baseline).
func (s *Store) Current() *RecPolicy {
	if p := s.ptr.Load(); p != nil {
		return p
	}
	return Baseline()
}

// EffectiveHash returns the sha256 hash of the live policy (consistency signal).
func (s *Store) EffectiveHash() string {
	if h := s.hash.Load(); h != nil {
		return *h
	}
	return ""
}

// Apply validates raw YAML and atomically swaps the live policy on success.
// On failure it returns the (unchanged) effective hash and the error; the
// previous last-good policy is retained.
func (s *Store) Apply(raw []byte) (string, error) {
	p, err := Parse(raw)
	if err != nil {
		return s.EffectiveHash(), err
	}
	s.swap(p)
	return s.EffectiveHash(), nil
}

// ApplyFile reads a YAML file and applies it. A read error leaves last-good in
// place and returns the unchanged hash plus the error.
func (s *Store) ApplyFile(path string) (string, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return s.EffectiveHash(), err
	}
	return s.Apply(raw)
}

func policyHash(p *RecPolicy) string {
	b, err := json.Marshal(p)
	if err != nil {
		return ""
	}
	sum := sha256.Sum256(b)
	return hex.EncodeToString(sum[:])
}
