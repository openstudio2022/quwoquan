package recommendation

import (
	"context"
	"fmt"
	"sync"
	"time"
)

type MemoryRedis struct {
	mu      sync.RWMutex
	strings map[string]string
	sets    map[string]map[string]struct{}
	hashes  map[string]map[string]float64
}

func NewMemoryRedis() *MemoryRedis {
	return &MemoryRedis{
		strings: map[string]string{},
		sets:    map[string]map[string]struct{}{},
		hashes:  map[string]map[string]float64{},
	}
}

func (m *MemoryRedis) Get(_ context.Context, key string) (string, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	if v, ok := m.strings[key]; ok {
		return v, nil
	}
	return "", fmt.Errorf("key not found: %s", key)
}

func (m *MemoryRedis) Set(_ context.Context, key string, value string, _ time.Duration) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.strings[key] = value
	return nil
}

func (m *MemoryRedis) Del(_ context.Context, keys ...string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, key := range keys {
		delete(m.strings, key)
		delete(m.sets, key)
		delete(m.hashes, key)
	}
	return nil
}

func (m *MemoryRedis) SAdd(_ context.Context, key string, members ...string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, ok := m.sets[key]; !ok {
		m.sets[key] = map[string]struct{}{}
	}
	for _, member := range members {
		m.sets[key][member] = struct{}{}
	}
	return nil
}

func (m *MemoryRedis) SMembers(_ context.Context, key string) ([]string, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	set := m.sets[key]
	out := make([]string, 0, len(set))
	for member := range set {
		out = append(out, member)
	}
	return out, nil
}

func (m *MemoryRedis) SIsMember(_ context.Context, key string, member string) (bool, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	_, ok := m.sets[key][member]
	return ok, nil
}

func (m *MemoryRedis) HIncrByFloat(_ context.Context, key, field string, incr float64) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, ok := m.hashes[key]; !ok {
		m.hashes[key] = map[string]float64{}
	}
	m.hashes[key][field] += incr
	return nil
}

func (m *MemoryRedis) HGetAll(_ context.Context, key string) (map[string]string, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	source := m.hashes[key]
	out := make(map[string]string, len(source))
	for k, v := range source {
		out[k] = fmt.Sprintf("%f", v)
	}
	return out, nil
}

func (m *MemoryRedis) Expire(_ context.Context, _ string, _ time.Duration) error {
	return nil
}
