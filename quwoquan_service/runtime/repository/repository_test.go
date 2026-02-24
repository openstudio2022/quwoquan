package repository

import (
	"context"
	"encoding/json"
	"testing"
)

type memCache struct {
	data map[string][]byte
}

func newMemCache() *memCache { return &memCache{data: make(map[string][]byte)} }

func (m *memCache) Get(_ context.Context, key string) ([]byte, error) { return m.data[key], nil }
func (m *memCache) Set(_ context.Context, key string, value []byte, _ int) error {
	m.data[key] = value
	return nil
}
func (m *memCache) Del(_ context.Context, key string) error { delete(m.data, key); return nil }

type memRepo struct {
	store map[string]map[string]any
}

func newMemRepo() *memRepo { return &memRepo{store: make(map[string]map[string]any)} }

func (m *memRepo) FindByID(_ context.Context, id string) (*map[string]any, error) {
	if e, ok := m.store[id]; ok {
		return &e, nil
	}
	return nil, nil
}
func (m *memRepo) FindAll(_ context.Context, _ Query) (*Page[map[string]any], error) {
	var items []map[string]any
	for _, v := range m.store {
		items = append(items, v)
	}
	return &Page[map[string]any]{Items: items, Total: int64(len(items))}, nil
}
func (m *memRepo) Create(_ context.Context, entity *map[string]any) error {
	id, _ := (*entity)["_id"].(string)
	m.store[id] = *entity
	return nil
}
func (m *memRepo) Update(_ context.Context, id string, entity *map[string]any) error {
	m.store[id] = *entity
	return nil
}
func (m *memRepo) Delete(_ context.Context, id string) error {
	delete(m.store, id)
	return nil
}
func (m *memRepo) Count(_ context.Context, _ Filter) (int64, error) {
	return int64(len(m.store)), nil
}

func TestCachedRepository_ReadThrough(t *testing.T) {
	inner := newMemRepo()
	cache := newMemCache()
	repo := NewCachedRepository(inner, cache, "TestEntity", 300)

	inner.store["e1"] = map[string]any{"_id": "e1", "name": "test"}

	result, err := repo.FindByIDCached(context.Background(), "e1")
	if err != nil {
		t.Fatalf("FindByIDCached: %v", err)
	}
	if result == nil || (*result)["name"] != "test" {
		t.Error("expected entity from inner repo")
	}

	// Should be cached now
	if cache.data["cache:TestEntity:e1"] == nil {
		t.Error("expected cache entry after read-through")
	}

	// Modify inner, cached should still return old
	inner.store["e1"]["name"] = "modified"
	result2, _ := repo.FindByIDCached(context.Background(), "e1")
	if (*result2)["name"] != "test" {
		t.Error("expected cached value, not modified value")
	}
}

func TestCachedRepository_InvalidateOnUpdate(t *testing.T) {
	inner := newMemRepo()
	cache := newMemCache()
	repo := NewCachedRepository(inner, cache, "TestEntity", 300)

	entity := map[string]any{"_id": "e1", "name": "original"}
	inner.store["e1"] = entity

	// Prime cache
	repo.FindByIDCached(context.Background(), "e1")

	// Update should invalidate cache
	updated := map[string]any{"_id": "e1", "name": "updated"}
	repo.Update(context.Background(), "e1", &updated)

	if cache.data["cache:TestEntity:e1"] != nil {
		t.Error("cache should be invalidated after update")
	}
}

func TestCachedRepository_InvalidateOnDelete(t *testing.T) {
	inner := newMemRepo()
	cache := newMemCache()
	repo := NewCachedRepository(inner, cache, "TestEntity", 300)

	entity := map[string]any{"_id": "e1", "name": "test"}
	inner.store["e1"] = entity

	repo.FindByIDCached(context.Background(), "e1")
	repo.Delete(context.Background(), "e1")

	if cache.data["cache:TestEntity:e1"] != nil {
		t.Error("cache should be invalidated after delete")
	}
}

func TestCachedRepository_CacheMiss(t *testing.T) {
	inner := newMemRepo()
	cache := newMemCache()
	repo := NewCachedRepository(inner, cache, "TestEntity", 300)

	result, err := repo.FindByIDCached(context.Background(), "nonexistent")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != nil {
		t.Error("expected nil for nonexistent entity")
	}
}

func TestQuery_FilterAndSort(t *testing.T) {
	q := Query{
		Filter: Filter{
			Conditions: []Condition{{Field: "status", Operator: Eq, Value: "active"}},
		},
		Sort:  []SortField{{Field: "created_at", Direction: Desc}},
		Limit: 10,
	}

	if q.Filter.Conditions[0].Field != "status" {
		t.Error("filter field mismatch")
	}
	if q.Sort[0].Direction != Desc {
		t.Error("sort should be descending")
	}
}

func TestPage_Serialization(t *testing.T) {
	page := Page[map[string]any]{
		Items: []map[string]any{{"_id": "1", "name": "a"}},
		Total: 1,
	}
	data, err := json.Marshal(page)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if len(data) == 0 {
		t.Error("expected non-empty JSON")
	}
}

func TestDomainEvent_Fields(t *testing.T) {
	e := DomainEvent{
		Type:        "PostCreated",
		AggregateID: "p1",
		Payload:     map[string]any{"title": "test"},
	}
	if e.Type != "PostCreated" {
		t.Error("event type mismatch")
	}
	if e.Payload["title"] != "test" {
		t.Error("payload mismatch")
	}
}
