package redis

import (
	"context"
	"sort"
	"sync"
	"time"
)

// memoryClient implements Client using in-memory maps.
// Thread-safe, suitable for dev/test environments.
type memoryClient struct {
	mu      sync.RWMutex
	strings map[string]memEntry
	hashes  map[string]map[string]string
	sets    map[string]map[string]struct{}
	zsets   map[string]map[string]float64
	subs    map[string][]chan Message
	subsMu  sync.RWMutex
}

type memEntry struct {
	strVal  string
	binVal  []byte
	expires time.Time
}

func (e memEntry) expired() bool {
	return !e.expires.IsZero() && time.Now().After(e.expires)
}

// NewMemoryClient returns an in-memory Client (no external Redis required).
func NewMemoryClient() Client {
	return &memoryClient{
		strings: make(map[string]memEntry),
		hashes:  make(map[string]map[string]string),
		sets:    make(map[string]map[string]struct{}),
		zsets:   make(map[string]map[string]float64),
		subs:    make(map[string][]chan Message),
	}
}

func (m *memoryClient) Get(_ context.Context, key string) (string, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	e, ok := m.strings[key]
	if !ok || e.expired() {
		return "", ErrKeyNotFound
	}
	return e.strVal, nil
}

func (m *memoryClient) GetBytes(_ context.Context, key string) ([]byte, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	e, ok := m.strings[key]
	if !ok || e.expired() {
		return nil, ErrKeyNotFound
	}
	return e.binVal, nil
}

func (m *memoryClient) Set(_ context.Context, key, value string, ttl time.Duration) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	e := memEntry{strVal: value, binVal: []byte(value)}
	if ttl > 0 {
		e.expires = time.Now().Add(ttl)
	}
	m.strings[key] = e
	return nil
}

func (m *memoryClient) SetBytes(_ context.Context, key string, value []byte, ttl time.Duration) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	e := memEntry{strVal: string(value), binVal: value}
	if ttl > 0 {
		e.expires = time.Now().Add(ttl)
	}
	m.strings[key] = e
	return nil
}

func (m *memoryClient) SetNX(_ context.Context, key, value string, ttl time.Duration) (bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if e, ok := m.strings[key]; ok && !e.expired() {
		return false, nil
	}
	e := memEntry{strVal: value, binVal: []byte(value)}
	if ttl > 0 {
		e.expires = time.Now().Add(ttl)
	}
	m.strings[key] = e
	return true, nil
}

func (m *memoryClient) Del(_ context.Context, keys ...string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, k := range keys {
		delete(m.strings, k)
		delete(m.hashes, k)
		delete(m.sets, k)
		delete(m.zsets, k)
	}
	return nil
}

func (m *memoryClient) Incr(_ context.Context, key string) (int64, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	e, ok := m.strings[key]
	var val int64
	if ok && !e.expired() {
		for _, c := range e.strVal {
			if c >= '0' && c <= '9' {
				val = val*10 + int64(c-'0')
			} else if c == '-' {
				// handled below
			}
		}
		if len(e.strVal) > 0 && e.strVal[0] == '-' {
			val = -val
		}
	}
	val++
	newStr := intToStr(val)
	exp := e.expires
	m.strings[key] = memEntry{strVal: newStr, binVal: []byte(newStr), expires: exp}
	return val, nil
}

func intToStr(v int64) string {
	if v == 0 {
		return "0"
	}
	neg := v < 0
	if neg {
		v = -v
	}
	buf := make([]byte, 0, 20)
	for v > 0 {
		buf = append(buf, byte('0'+v%10))
		v /= 10
	}
	if neg {
		buf = append(buf, '-')
	}
	for i, j := 0, len(buf)-1; i < j; i, j = i+1, j-1 {
		buf[i], buf[j] = buf[j], buf[i]
	}
	return string(buf)
}

func (m *memoryClient) Expire(_ context.Context, key string, ttl time.Duration) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if e, ok := m.strings[key]; ok {
		e.expires = time.Now().Add(ttl)
		m.strings[key] = e
	}
	return nil
}

// ── Hash ────────────────────────────────────────────────

func (m *memoryClient) HSet(_ context.Context, key, field, value string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	h, ok := m.hashes[key]
	if !ok {
		h = make(map[string]string)
		m.hashes[key] = h
	}
	h[field] = value
	return nil
}

func (m *memoryClient) HGet(_ context.Context, key, field string) (string, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	h, ok := m.hashes[key]
	if !ok {
		return "", ErrKeyNotFound
	}
	v, ok := h[field]
	if !ok {
		return "", ErrKeyNotFound
	}
	return v, nil
}

func (m *memoryClient) HDel(_ context.Context, key string, fields ...string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	h, ok := m.hashes[key]
	if !ok {
		return nil
	}
	for _, f := range fields {
		delete(h, f)
	}
	return nil
}

func (m *memoryClient) HGetAll(_ context.Context, key string) (map[string]string, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	h, ok := m.hashes[key]
	if !ok {
		return map[string]string{}, nil
	}
	cp := make(map[string]string, len(h))
	for k, v := range h {
		cp[k] = v
	}
	return cp, nil
}

func (m *memoryClient) HIncrByFloat(_ context.Context, key, field string, incr float64) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	h, ok := m.hashes[key]
	if !ok {
		h = make(map[string]string)
		m.hashes[key] = h
	}
	var cur float64
	if v, exists := h[field]; exists {
		_, _ = parseFloat(v, &cur)
	}
	cur += incr
	h[field] = formatFloat(cur)
	return nil
}

func parseFloat(s string, out *float64) (int, error) {
	// Minimal float parser for in-memory implementation.
	var val float64
	neg := false
	i := 0
	if i < len(s) && s[i] == '-' {
		neg = true
		i++
	}
	for ; i < len(s) && s[i] >= '0' && s[i] <= '9'; i++ {
		val = val*10 + float64(s[i]-'0')
	}
	if i < len(s) && s[i] == '.' {
		i++
		frac := 0.1
		for ; i < len(s) && s[i] >= '0' && s[i] <= '9'; i++ {
			val += float64(s[i]-'0') * frac
			frac /= 10
		}
	}
	if neg {
		val = -val
	}
	*out = val
	return i, nil
}

func formatFloat(v float64) string {
	// Use fmt-free approach for simple cases.
	if v == 0 {
		return "0"
	}
	neg := v < 0
	if neg {
		v = -v
	}
	intPart := int64(v)
	fracPart := v - float64(intPart)

	s := intToStr(intPart)
	if fracPart > 0.0000001 {
		s += "."
		for i := 0; i < 6 && fracPart > 0.0000001; i++ {
			fracPart *= 10
			digit := int(fracPart)
			s += string(rune('0' + digit))
			fracPart -= float64(digit)
		}
	}
	if neg {
		s = "-" + s
	}
	return s
}

// ── Set ─────────────────────────────────────────────────

func (m *memoryClient) SAdd(_ context.Context, key string, members ...string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	s, ok := m.sets[key]
	if !ok {
		s = make(map[string]struct{})
		m.sets[key] = s
	}
	for _, mb := range members {
		s[mb] = struct{}{}
	}
	return nil
}

func (m *memoryClient) SMembers(_ context.Context, key string) ([]string, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	s, ok := m.sets[key]
	if !ok {
		return []string{}, nil
	}
	result := make([]string, 0, len(s))
	for mb := range s {
		result = append(result, mb)
	}
	return result, nil
}

func (m *memoryClient) SIsMember(_ context.Context, key, member string) (bool, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	s, ok := m.sets[key]
	if !ok {
		return false, nil
	}
	_, exists := s[member]
	return exists, nil
}

func (m *memoryClient) ZAdd(_ context.Context, key string, score float64, member string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	z, ok := m.zsets[key]
	if !ok {
		z = make(map[string]float64)
		m.zsets[key] = z
	}
	z[member] = score
	return nil
}

func (m *memoryClient) ZRangeByScore(_ context.Context, key string, min, max float64, limit int) ([]string, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	z, ok := m.zsets[key]
	if !ok {
		return []string{}, nil
	}
	type entry struct {
		member string
		score  float64
	}
	items := make([]entry, 0, len(z))
	for member, score := range z {
		if score < min || score > max {
			continue
		}
		items = append(items, entry{member: member, score: score})
	}
	sort.Slice(items, func(i, j int) bool {
		if items[i].score == items[j].score {
			return items[i].member < items[j].member
		}
		return items[i].score < items[j].score
	})
	if limit > 0 && len(items) > limit {
		items = items[:limit]
	}
	result := make([]string, 0, len(items))
	for _, item := range items {
		result = append(result, item.member)
	}
	return result, nil
}

func (m *memoryClient) ZRem(_ context.Context, key string, members ...string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	z, ok := m.zsets[key]
	if !ok {
		return nil
	}
	for _, member := range members {
		delete(z, member)
	}
	return nil
}

func (m *memoryClient) ZCard(_ context.Context, key string) (int64, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return int64(len(m.zsets[key])), nil
}

// ── Pub/Sub ─────────────────────────────────────────────

func (m *memoryClient) Publish(_ context.Context, channel, message string) error {
	m.subsMu.RLock()
	defer m.subsMu.RUnlock()
	for _, ch := range m.subs[channel] {
		select {
		case ch <- Message{Channel: channel, Payload: message}:
		default:
		}
	}
	return nil
}

func (m *memoryClient) Subscribe(_ context.Context, channels ...string) (Subscription, error) {
	ch := make(chan Message, 64)
	m.subsMu.Lock()
	for _, c := range channels {
		m.subs[c] = append(m.subs[c], ch)
	}
	m.subsMu.Unlock()
	return &memSub{ch: ch, parent: m, channels: channels}, nil
}

type memSub struct {
	ch       chan Message
	parent   *memoryClient
	channels []string
}

func (s *memSub) Channel() <-chan Message { return s.ch }
func (s *memSub) Close() error {
	s.parent.subsMu.Lock()
	defer s.parent.subsMu.Unlock()
	for _, c := range s.channels {
		subs := s.parent.subs[c]
		for i, sub := range subs {
			if sub == s.ch {
				s.parent.subs[c] = append(subs[:i], subs[i+1:]...)
				break
			}
		}
	}
	close(s.ch)
	return nil
}

// ── Pipeline ────────────────────────────────────────────

func (m *memoryClient) Pipeline(_ context.Context) Pipeliner {
	return &memPipeline{m: m}
}

type memPipeline struct {
	m   *memoryClient
	ops []func()
}

func (p *memPipeline) Get(ctx context.Context, key string) *StringResult {
	r := &StringResult{}
	p.ops = append(p.ops, func() {
		r.val, r.err = p.m.Get(ctx, key)
	})
	return r
}

func (p *memPipeline) Set(ctx context.Context, key, value string, ttl time.Duration) {
	p.ops = append(p.ops, func() {
		_ = p.m.Set(ctx, key, value, ttl)
	})
}

func (p *memPipeline) HGetAll(ctx context.Context, key string) *MapResult {
	r := &MapResult{}
	p.ops = append(p.ops, func() {
		r.val, r.err = p.m.HGetAll(ctx, key)
	})
	return r
}

func (p *memPipeline) SMembers(ctx context.Context, key string) *SliceResult {
	r := &SliceResult{}
	p.ops = append(p.ops, func() {
		r.val, r.err = p.m.SMembers(ctx, key)
	})
	return r
}

func (p *memPipeline) Exec(_ context.Context) error {
	for _, op := range p.ops {
		op()
	}
	return nil
}

// ── Lifecycle ───────────────────────────────────────────

func (m *memoryClient) Close() error                 { return nil }
func (m *memoryClient) Ping(_ context.Context) error { return nil }
