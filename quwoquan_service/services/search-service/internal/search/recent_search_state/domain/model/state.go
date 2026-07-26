// Package model 定义 RecentSearchState 对象聚合：persona 在单一 scope 下的有界
// 最近搜索状态。entries 按语义键（scope+facet+normalized query）去重、
// 最近使用在前；并发由服务端内部 version CAS 承载（公开请求不携带版本）。
package model

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"time"
)

// MaxEntries 是单个 (persona, scope) 状态的条目上限；超限淘汰最旧条目。
const MaxEntries = 12

var (
	ErrInvalidQuery  = errors.New("recent search query is required")
	ErrEntryNotFound = errors.New("recent search entry not found")
)

// Entry 是一条最近搜索记录。EntryID 由服务端从语义键派生，客户端只读。
type Entry struct {
	EntryID   string    `bson:"entryId" json:"entryId"`
	Query     string    `bson:"query" json:"query"`
	Scope     string    `bson:"scope" json:"scope"`
	Facet     string    `bson:"facet,omitempty" json:"facet,omitempty"`
	UpdatedAt time.Time `bson:"updatedAt" json:"updatedAt"`
}

// State 是 (personaId, scope) 唯一的聚合文档。
type State struct {
	ID        string    `bson:"_id"`
	PersonaID string    `bson:"personaId"`
	Scope     string    `bson:"scope"`
	Entries   []Entry   `bson:"entries"`
	Version   int64     `bson:"version"`
	UpdatedAt time.Time `bson:"updatedAt"`
}

// NormalizeScope 统一 scope 缺省值。
func NormalizeScope(scope string) string {
	scope = strings.TrimSpace(strings.ToLower(scope))
	if scope == "" {
		return "all"
	}
	return scope
}

// NormalizeQuery 与语义键、去重使用同一归一化。
func NormalizeQuery(query string) string {
	return strings.ToLower(strings.TrimSpace(query))
}

// DeriveEntryID 从语义键派生稳定 entryId（跨平台/版本稳定，替代客户端 hashCode）。
func DeriveEntryID(scope, facet, query string) string {
	seed := NormalizeScope(scope) + "\x00" + strings.TrimSpace(facet) + "\x00" + NormalizeQuery(query)
	sum := sha256.Sum256([]byte(seed))
	return "recent_" + hex.EncodeToString(sum[:8])
}

// StateID 是聚合文档主键（persona+scope 派生，天然唯一）。
func StateID(personaID, scope string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(personaID) + "\x00" + NormalizeScope(scope)))
	return "recent_state_" + hex.EncodeToString(sum[:12])
}

// NewState 构造空状态（version=0，首次 Commit 时置 1）。
func NewState(personaID, scope string, now time.Time) State {
	scope = NormalizeScope(scope)
	return State{
		ID:        StateID(personaID, scope),
		PersonaID: strings.TrimSpace(personaID),
		Scope:     scope,
		Entries:   []Entry{},
		Version:   0,
		UpdatedAt: now.UTC(),
	}
}

// Upsert 记录/提升一条搜索：同语义键去重置顶，超限淘汰最旧；
// 返回条目与该操作是否改变了状态。同语义键条目已在顶部时目标状态已满足，
// 返回 changed=false（调用方按 no-op receipt 处理，并发同键写天然收敛）。
func (s *State) Upsert(query, facet string, now time.Time) (Entry, bool, error) {
	normalized := NormalizeQuery(query)
	if normalized == "" {
		return Entry{}, false, ErrInvalidQuery
	}
	entryID := DeriveEntryID(s.Scope, facet, query)
	if len(s.Entries) > 0 && s.Entries[0].EntryID == entryID {
		return s.Entries[0], false, nil
	}
	entry := Entry{
		EntryID:   entryID,
		Query:     strings.TrimSpace(query),
		Scope:     s.Scope,
		Facet:     strings.TrimSpace(facet),
		UpdatedAt: now.UTC(),
	}
	next := make([]Entry, 0, len(s.Entries)+1)
	next = append(next, entry)
	for _, existing := range s.Entries {
		if existing.EntryID == entry.EntryID {
			continue
		}
		next = append(next, existing)
	}
	if len(next) > MaxEntries {
		next = next[:MaxEntries]
	}
	s.Entries = next
	s.Version++
	s.UpdatedAt = now.UTC()
	return entry, true, nil
}

// Delete 删除单条；不存在返回 (false)，调用方按 no-op receipt 处理。
func (s *State) Delete(entryID string, now time.Time) bool {
	entryID = strings.TrimSpace(entryID)
	next := s.Entries[:0]
	removed := false
	for _, existing := range s.Entries {
		if existing.EntryID == entryID {
			removed = true
			continue
		}
		next = append(next, existing)
	}
	if !removed {
		return false
	}
	s.Entries = next
	s.Version++
	s.UpdatedAt = now.UTC()
	return true
}

// Clear 清空全部条目；已空返回 false（no-op）。
func (s *State) Clear(now time.Time) bool {
	if len(s.Entries) == 0 {
		return false
	}
	s.Entries = []Entry{}
	s.Version++
	s.UpdatedAt = now.UTC()
	return true
}
