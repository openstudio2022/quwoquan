package testsupport

import (
	"context"
	"fmt"
	"sync"
	"time"
)

// FakeRedis is a deterministic local-contract adapter. Production code cannot
// reach this package because only *_test.go callers import internal/testsupport.
type FakeRedis struct {
	mu      sync.RWMutex
	strings map[string]string
	sets    map[string]map[string]struct{}
	hashes  map[string]map[string]float64
}

func NewFakeRedis() *FakeRedis {
	return &FakeRedis{
		strings: map[string]string{},
		sets:    map[string]map[string]struct{}{},
		hashes:  map[string]map[string]float64{},
	}
}

func (f *FakeRedis) Get(_ context.Context, key string) (string, error) {
	f.mu.RLock()
	defer f.mu.RUnlock()
	if value, ok := f.strings[key]; ok {
		return value, nil
	}
	return "", fmt.Errorf("key not found: %s", key)
}

func (f *FakeRedis) Set(_ context.Context, key, value string, _ time.Duration) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.strings[key] = value
	return nil
}

func (f *FakeRedis) SetNX(_ context.Context, key, value string, _ time.Duration) (bool, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if _, exists := f.strings[key]; exists {
		return false, nil
	}
	f.strings[key] = value
	return true, nil
}

func (f *FakeRedis) Del(_ context.Context, keys ...string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	for _, key := range keys {
		delete(f.strings, key)
		delete(f.sets, key)
		delete(f.hashes, key)
	}
	return nil
}

func (f *FakeRedis) SAdd(_ context.Context, key string, members ...string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if _, exists := f.sets[key]; !exists {
		f.sets[key] = map[string]struct{}{}
	}
	for _, member := range members {
		f.sets[key][member] = struct{}{}
	}
	return nil
}

func (f *FakeRedis) SMembers(_ context.Context, key string) ([]string, error) {
	f.mu.RLock()
	defer f.mu.RUnlock()
	out := make([]string, 0, len(f.sets[key]))
	for member := range f.sets[key] {
		out = append(out, member)
	}
	return out, nil
}

func (f *FakeRedis) SIsMember(_ context.Context, key, member string) (bool, error) {
	f.mu.RLock()
	defer f.mu.RUnlock()
	_, exists := f.sets[key][member]
	return exists, nil
}

func (f *FakeRedis) HIncrByFloat(_ context.Context, key, field string, increment float64) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if _, exists := f.hashes[key]; !exists {
		f.hashes[key] = map[string]float64{}
	}
	f.hashes[key][field] += increment
	return nil
}

func (f *FakeRedis) HGetAll(_ context.Context, key string) (map[string]string, error) {
	f.mu.RLock()
	defer f.mu.RUnlock()
	out := make(map[string]string, len(f.hashes[key]))
	for field, value := range f.hashes[key] {
		out[field] = fmt.Sprintf("%f", value)
	}
	return out, nil
}

func (f *FakeRedis) Expire(_ context.Context, _ string, _ time.Duration) error { return nil }
