package controlplane

import (
	"sync"
)

type HotConfigStore struct {
	mu     sync.RWMutex
	values map[string]ResolvedConfigValue
	hash   string
}

func NewHotConfigStore() *HotConfigStore {
	return &HotConfigStore{values: map[string]ResolvedConfigValue{}}
}

func (s *HotConfigStore) Apply(resolved []ResolvedConfigValue) string {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.values = make(map[string]ResolvedConfigValue, len(resolved))
	for _, v := range resolved {
		s.values[v.Key] = v
	}
	s.hash = EffectiveConfigHash(resolved)
	return s.hash
}

func (s *HotConfigStore) Get(key string) (any, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	v, ok := s.values[key]
	if !ok {
		return nil, false
	}
	return v.Value, true
}

func (s *HotConfigStore) GetInt(key string, fallback int) int {
	raw, ok := s.Get(key)
	if !ok {
		return fallback
	}
	switch v := raw.(type) {
	case float64:
		return int(v)
	case int:
		return v
	default:
		return fallback
	}
}

func (s *HotConfigStore) GetFloat(key string, fallback float64) float64 {
	raw, ok := s.Get(key)
	if !ok {
		return fallback
	}
	switch v := raw.(type) {
	case float64:
		return v
	case int:
		return float64(v)
	default:
		return fallback
	}
}

// GetString 读取字符串型热配置值（如运营态错误提示语 override）。
// HotConfigStore.Value 为 any，天然承载字符串；未命中或类型不符返回 fallback。
func (s *HotConfigStore) GetString(key string, fallback string) string {
	raw, ok := s.Get(key)
	if !ok {
		return fallback
	}
	if v, ok := raw.(string); ok {
		return v
	}
	return fallback
}

func (s *HotConfigStore) GetBool(key string, fallback bool) bool {
	raw, ok := s.Get(key)
	if !ok {
		return fallback
	}
	if v, ok := raw.(bool); ok {
		return v
	}
	return fallback
}

func (s *HotConfigStore) EffectiveHash() string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.hash
}

func (s *HotConfigStore) Snapshot() map[string]ResolvedConfigValue {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := make(map[string]ResolvedConfigValue, len(s.values))
	for k, v := range s.values {
		out[k] = v
	}
	return out
}
