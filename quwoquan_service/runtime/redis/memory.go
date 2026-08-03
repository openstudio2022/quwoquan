package redis

import (
	"context"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"quwoquan_service/runtime/boundedrecord"
)

// memoryClient implements Client using in-memory maps.
// Thread-safe, suitable for dev/test environments.
type memoryClient struct {
	mu                     sync.RWMutex
	strings                map[string]memEntry
	hashes                 map[string]map[string]string
	hashExpirations        map[string]time.Time
	sets                   map[string]map[string]struct{}
	zsets                  map[string]map[string]float64
	immutableRecordIndexes map[string]map[string]memoryImmutableRecordMetadata
	streams                map[string]*memStream
	subs                   map[string][]chan Message
	subsMu                 sync.RWMutex
}

type memStream struct {
	lastMS  int64
	nextSeq int64
	groups  map[string]*memStreamGroup
	entries []StreamMessage
}

type memStreamGroup struct {
	lastDelivered int
	pending       map[string]StreamMessage
}

type memEntry struct {
	strVal  string
	binVal  []byte
	expires time.Time
}

type memoryImmutableRecordMetadata struct {
	ownerDigest  string
	payloadBytes int64
	createdAt    time.Time
	expiresAt    time.Time
}

func (e memEntry) expired() bool {
	return !e.expires.IsZero() && time.Now().After(e.expires)
}

// NewMemoryClient returns an in-memory Client (no external Redis required).
func NewMemoryClient() Client {
	return &memoryClient{
		strings:         make(map[string]memEntry),
		hashes:          make(map[string]map[string]string),
		hashExpirations: make(map[string]time.Time),
		sets:            make(map[string]map[string]struct{}),
		zsets:           make(map[string]map[string]float64),
		immutableRecordIndexes: make(
			map[string]map[string]memoryImmutableRecordMetadata,
		),
		streams: make(map[string]*memStream),
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

func (m *memoryClient) GetDel(_ context.Context, key string) (string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	e, ok := m.strings[key]
	if !ok || e.expired() {
		delete(m.strings, key)
		return "", ErrKeyNotFound
	}
	delete(m.strings, key)
	return e.strVal, nil
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

func (m *memoryClient) CreateBoundedImmutableRecordAtomic(
	_ context.Context,
	request boundedrecord.Request,
) (boundedrecord.Result, error) {
	if err := request.Validate(); err != nil {
		return boundedrecord.Result{}, err
	}

	m.mu.Lock()
	defer m.mu.Unlock()
	now := time.Now()
	index := m.immutableRecordIndexes[request.ShardIndexKey]
	if index == nil {
		index = make(map[string]memoryImmutableRecordMetadata)
		m.immutableRecordIndexes[request.ShardIndexKey] = index
	}
	if len(index) > request.Policy.MaximumLiveRecordsPerShard {
		return boundedrecord.Result{}, boundedrecord.ErrRepairBound
	}
	for indexedKey, metadata := range index {
		entry, exists := m.strings[indexedKey]
		if !exists || entry.expires.IsZero() || !entry.expires.After(now) ||
			!metadata.expiresAt.After(now) {
			delete(index, indexedKey)
			delete(m.strings, indexedKey)
		}
	}

	if entry, exists := m.strings[request.RecordKey]; exists {
		if entry.expires.IsZero() || !entry.expires.After(now) {
			delete(m.strings, request.RecordKey)
			delete(index, request.RecordKey)
		} else {
			metadata, indexed := index[request.RecordKey]
			if !indexed || metadata.ownerDigest != request.OwnerDigest ||
				metadata.payloadBytes != int64(len(entry.strVal)) {
				return boundedrecord.Result{}, boundedrecord.ErrRepairBound
			}
			liveRecords, liveBytes := memoryImmutableRecordUsage(index)
			return boundedrecord.Result{
				Winner:        entry.strVal,
				UsageMeasured: true,
				LiveRecords:   liveRecords,
				LiveBytes:     liveBytes,
			}, nil
		}
	}

	ownerVictims, ownerEvictionBytes := oldestMemoryImmutableOwnerRecords(
		index,
		request.OwnerDigest,
		request.Policy.MaximumLiveRecordsPerOwner-1,
	)
	liveRecords, liveBytes := memoryImmutableRecordUsage(index)
	projectedRecords := liveRecords - int64(len(ownerVictims)) + 1
	projectedBytes := liveBytes - ownerEvictionBytes +
		int64(len(request.Value))
	if projectedRecords > int64(request.Policy.MaximumLiveRecordsPerShard) {
		return boundedrecord.Result{
			UsageMeasured: true,
			LiveRecords:   liveRecords,
			LiveBytes:     liveBytes,
		}, boundedrecord.ErrShardKeyQuota
	}
	if projectedBytes > request.Policy.MaximumLiveBytesPerShard {
		return boundedrecord.Result{
			UsageMeasured: true,
			LiveRecords:   liveRecords,
			LiveBytes:     liveBytes,
		}, boundedrecord.ErrShardByteQuota
	}
	for _, victim := range ownerVictims {
		delete(index, victim)
		delete(m.strings, victim)
	}
	expiresAt := now.Add(request.TTL)
	m.strings[request.RecordKey] = memEntry{
		strVal:  request.Value,
		binVal:  []byte(request.Value),
		expires: expiresAt,
	}
	index[request.RecordKey] = memoryImmutableRecordMetadata{
		ownerDigest:  request.OwnerDigest,
		payloadBytes: int64(len(request.Value)),
		createdAt:    now,
		expiresAt:    expiresAt,
	}
	return boundedrecord.Result{
		Created:       true,
		OwnerEvicted:  int64(len(ownerVictims)),
		UsageMeasured: true,
		LiveRecords:   projectedRecords,
		LiveBytes:     projectedBytes,
	}, nil
}

func memoryImmutableRecordUsage(
	index map[string]memoryImmutableRecordMetadata,
) (int64, int64) {
	var bytes int64
	for _, metadata := range index {
		bytes += metadata.payloadBytes
	}
	return int64(len(index)), bytes
}

func oldestMemoryImmutableOwnerRecords(
	index map[string]memoryImmutableRecordMetadata,
	ownerDigest string,
	maxActiveForOwner int,
) ([]string, int64) {
	working := make(map[string]memoryImmutableRecordMetadata, len(index))
	for key, metadata := range index {
		working[key] = metadata
	}
	var victims []string
	var victimBytes int64
	for {
		ownerCount := 0
		oldestKey := ""
		var oldestCreatedAt time.Time
		for candidateKey, metadata := range working {
			if metadata.ownerDigest != ownerDigest {
				continue
			}
			ownerCount++
			if oldestKey == "" || metadata.createdAt.Before(oldestCreatedAt) ||
				(metadata.createdAt.Equal(oldestCreatedAt) &&
					candidateKey < oldestKey) {
				oldestKey = candidateKey
				oldestCreatedAt = metadata.createdAt
			}
		}
		if ownerCount <= maxActiveForOwner || oldestKey == "" {
			break
		}
		victimBytes += working[oldestKey].payloadBytes
		delete(working, oldestKey)
		victims = append(victims, oldestKey)
	}
	return victims, victimBytes
}

func (m *memoryClient) Del(_ context.Context, keys ...string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, k := range keys {
		delete(m.strings, k)
		delete(m.hashes, k)
		delete(m.sets, k)
		delete(m.zsets, k)
		delete(m.immutableRecordIndexes, k)
		for _, index := range m.immutableRecordIndexes {
			delete(index, k)
		}
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
	if _, ok := m.hashes[key]; ok {
		m.hashExpirations[key] = time.Now().Add(ttl)
	}
	return nil
}

// ── Hash ────────────────────────────────────────────────

func (m *memoryClient) HSet(_ context.Context, key, field, value string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.expireHashLocked(key)
	h, ok := m.hashes[key]
	if !ok {
		h = make(map[string]string)
		m.hashes[key] = h
	}
	h[field] = value
	return nil
}

func (m *memoryClient) HGet(_ context.Context, key, field string) (string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.expireHashLocked(key)
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
	m.expireHashLocked(key)
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
	m.mu.Lock()
	defer m.mu.Unlock()
	m.expireHashLocked(key)
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

func (m *memoryClient) CompareAndSwapHashField(
	_ context.Context,
	key string,
	field string,
	expected *string,
	replacement *string,
	ttl time.Duration,
) (bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.expireHashLocked(key)
	hash, exists := m.hashes[key]
	current, fieldExists := "", false
	if exists {
		current, fieldExists = hash[field]
	}
	if expected == nil {
		if fieldExists {
			return false, nil
		}
	} else if !fieldExists || current != *expected {
		return false, nil
	}
	if replacement == nil {
		if exists {
			delete(hash, field)
			if len(hash) == 0 {
				delete(m.hashes, key)
				delete(m.hashExpirations, key)
			}
		}
		return true, nil
	}
	if !exists {
		hash = make(map[string]string)
		m.hashes[key] = hash
	}
	hash[field] = *replacement
	if ttl > 0 {
		m.hashExpirations[key] = time.Now().Add(ttl)
	}
	return true, nil
}

func (m *memoryClient) expireHashLocked(key string) {
	expiresAt, ok := m.hashExpirations[key]
	if !ok || expiresAt.IsZero() || time.Now().Before(expiresAt) {
		return
	}
	delete(m.hashes, key)
	delete(m.hashExpirations, key)
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

func (m *memoryClient) SRem(_ context.Context, key string, members ...string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	s, ok := m.sets[key]
	if !ok {
		return nil
	}
	for _, mb := range members {
		delete(s, mb)
	}
	if len(s) == 0 {
		delete(m.sets, key)
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

func (m *memoryClient) XGroupCreateMkStream(_ context.Context, stream string, group string, start string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	ms := m.ensureStream(stream)
	if _, ok := ms.groups[group]; !ok {
		lastDelivered := 0
		if start == "$" {
			lastDelivered = len(ms.entries)
		}
		ms.groups[group] = &memStreamGroup{
			lastDelivered: lastDelivered,
			pending:       map[string]StreamMessage{},
		}
	}
	return nil
}

func (m *memoryClient) XAdd(_ context.Context, stream string, values map[string]string) (string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	ms := m.ensureStream(stream)
	nowMS := time.Now().UnixMilli()
	if nowMS <= ms.lastMS {
		nowMS = ms.lastMS
		ms.nextSeq++
	} else {
		ms.lastMS = nowMS
		ms.nextSeq = 0
	}
	id := intToStr(nowMS) + "-" + intToStr(ms.nextSeq)
	copied := make(map[string]string, len(values))
	for key, value := range values {
		copied[key] = value
	}
	ms.entries = append(ms.entries, StreamMessage{Stream: stream, ID: id, Values: copied})
	return id, nil
}

func (m *memoryClient) XRead(
	ctx context.Context,
	streams map[string]string,
	count int64,
	block time.Duration,
) ([]StreamMessage, error) {
	deadline := time.Now().Add(block)
	for {
		m.mu.RLock()
		out := make([]StreamMessage, 0)
		streamNames := make([]string, 0, len(streams))
		for stream := range streams {
			streamNames = append(streamNames, stream)
		}
		sort.Strings(streamNames)
		for _, stream := range streamNames {
			cursorMS, cursorSequence, err := parseMemoryStreamID(streams[stream])
			if err != nil {
				m.mu.RUnlock()
				return nil, err
			}
			ms := m.streams[stream]
			if ms == nil {
				continue
			}
			for _, message := range ms.entries {
				messageMS, messageSequence, parseErr := parseMemoryStreamID(message.ID)
				if parseErr != nil {
					m.mu.RUnlock()
					return nil, parseErr
				}
				if messageMS < cursorMS ||
					(messageMS == cursorMS && messageSequence <= cursorSequence) {
					continue
				}
				message.Values = cloneStreamValues(message.Values)
				out = append(out, message)
				if count > 0 && int64(len(out)) >= count {
					break
				}
			}
			if count > 0 && int64(len(out)) >= count {
				break
			}
		}
		m.mu.RUnlock()
		if len(out) > 0 || block <= 0 || time.Now().After(deadline) {
			return out, nil
		}
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(10 * time.Millisecond):
		}
	}
}

func (m *memoryClient) XReadGroup(
	_ context.Context,
	group string,
	consumer string,
	streams map[string]string,
	count int64,
	block time.Duration,
) ([]StreamMessage, error) {
	deadline := time.Now().Add(block)
	for {
		m.mu.Lock()
		out := make([]StreamMessage, 0)
		streamNames := make([]string, 0, len(streams))
		for stream := range streams {
			streamNames = append(streamNames, stream)
		}
		sort.Strings(streamNames)
		for _, stream := range streamNames {
			ms := m.ensureStream(stream)
			g := ms.groups[group]
			if g == nil {
				g = &memStreamGroup{pending: map[string]StreamMessage{}}
				ms.groups[group] = g
			}
			start := streams[stream]
			if start != ">" {
				for _, msg := range g.pending {
					out = append(out, msg)
					if count > 0 && int64(len(out)) >= count {
						break
					}
				}
			} else {
				for g.lastDelivered < len(ms.entries) {
					msg := ms.entries[g.lastDelivered]
					g.lastDelivered++
					msg.Values = cloneStreamValues(msg.Values)
					msg.Values["consumer"] = consumer
					g.pending[msg.ID] = msg
					out = append(out, msg)
					if count > 0 && int64(len(out)) >= count {
						break
					}
				}
			}
			if count > 0 && int64(len(out)) >= count {
				break
			}
		}
		m.mu.Unlock()
		if len(out) > 0 || block <= 0 || time.Now().After(deadline) {
			return out, nil
		}
		time.Sleep(10 * time.Millisecond)
	}
}

func (m *memoryClient) XAck(_ context.Context, stream string, group string, ids ...string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	ms := m.ensureStream(stream)
	g := ms.groups[group]
	if g == nil {
		return nil
	}
	for _, id := range ids {
		delete(g.pending, id)
	}
	return nil
}

func (m *memoryClient) XAutoClaim(
	_ context.Context,
	stream string,
	group string,
	consumer string,
	minIdle time.Duration,
	start string,
	count int64,
) ([]StreamMessage, string, error) {
	_ = consumer
	_ = minIdle
	_ = start
	m.mu.Lock()
	defer m.mu.Unlock()
	ms := m.ensureStream(stream)
	g := ms.groups[group]
	if g == nil {
		return nil, "0-0", nil
	}
	out := make([]StreamMessage, 0)
	for _, message := range g.pending {
		out = append(out, message)
		if count > 0 && int64(len(out)) >= count {
			break
		}
	}
	return out, "0-0", nil
}

func (m *memoryClient) XPendingCount(_ context.Context, stream string, group string) (int64, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	ms := m.ensureStream(stream)
	if currentGroup := ms.groups[group]; currentGroup != nil {
		return int64(len(currentGroup.pending)), nil
	}
	return 0, nil
}

func (m *memoryClient) XTrimOlderThan(
	_ context.Context,
	stream string,
	maxAge time.Duration,
) error {
	if maxAge <= 0 {
		return fmt.Errorf("Redis stream max age must be positive")
	}
	minID := fmt.Sprintf("%d-0", time.Now().Add(-maxAge).UnixMilli())
	minimumMS, minimumSequence, err := parseMemoryStreamID(minID)
	if err != nil {
		return err
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	ms := m.ensureStream(stream)
	removed := 0
	for removed < len(ms.entries) {
		entryMS, entrySequence, parseErr := parseMemoryStreamID(
			ms.entries[removed].ID,
		)
		if parseErr != nil {
			return parseErr
		}
		if entryMS > minimumMS ||
			(entryMS == minimumMS && entrySequence >= minimumSequence) {
			break
		}
		removed++
	}
	if removed == 0 {
		return nil
	}
	ms.entries = append([]StreamMessage(nil), ms.entries[removed:]...)
	for _, group := range ms.groups {
		group.lastDelivered -= removed
		if group.lastDelivered < 0 {
			group.lastDelivered = 0
		}
	}
	return nil
}

func parseMemoryStreamID(id string) (int64, int64, error) {
	parts := strings.Split(strings.TrimSpace(id), "-")
	if len(parts) != 2 {
		return 0, 0, fmt.Errorf("invalid Redis stream ID %q", id)
	}
	milliseconds, err := strconv.ParseInt(parts[0], 10, 64)
	if err != nil || milliseconds < 0 {
		return 0, 0, fmt.Errorf("invalid Redis stream ID %q", id)
	}
	sequence, err := strconv.ParseInt(parts[1], 10, 64)
	if err != nil || sequence < 0 {
		return 0, 0, fmt.Errorf("invalid Redis stream ID %q", id)
	}
	return milliseconds, sequence, nil
}

func (m *memoryClient) ensureStream(stream string) *memStream {
	ms := m.streams[stream]
	if ms == nil {
		ms = &memStream{groups: map[string]*memStreamGroup{}}
		m.streams[stream] = ms
	}
	return ms
}

func cloneStreamValues(values map[string]string) map[string]string {
	out := make(map[string]string, len(values))
	for key, value := range values {
		out[key] = value
	}
	return out
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

func (p *memPipeline) SIsMember(
	ctx context.Context,
	key string,
	member string,
) *BoolResult {
	r := &BoolResult{}
	p.ops = append(p.ops, func() {
		r.val, r.err = p.m.SIsMember(ctx, key, member)
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
