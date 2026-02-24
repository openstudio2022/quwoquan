package runtimecontext

import (
	"context"
	"fmt"
	"testing"
	"time"

	"quwoquan_service/runtime/recommendation"
)

type mockRedis struct {
	data map[string]string
	sets map[string]map[string]bool
	hash map[string]map[string]string
}

func newMockRedis() *mockRedis {
	return &mockRedis{
		data: make(map[string]string),
		sets: make(map[string]map[string]bool),
		hash: make(map[string]map[string]string),
	}
}

func (m *mockRedis) Get(_ context.Context, key string) (string, error) {
	return m.data[key], nil
}
func (m *mockRedis) Set(_ context.Context, key, value string, _ time.Duration) error {
	m.data[key] = value
	return nil
}
func (m *mockRedis) Del(_ context.Context, keys ...string) error {
	for _, k := range keys {
		delete(m.data, k)
	}
	return nil
}
func (m *mockRedis) SAdd(_ context.Context, key string, members ...string) error {
	if m.sets[key] == nil {
		m.sets[key] = make(map[string]bool)
	}
	for _, member := range members {
		m.sets[key][member] = true
	}
	return nil
}
func (m *mockRedis) SMembers(_ context.Context, key string) ([]string, error) {
	var out []string
	for member := range m.sets[key] {
		out = append(out, member)
	}
	return out, nil
}
func (m *mockRedis) SIsMember(_ context.Context, key, member string) (bool, error) {
	return m.sets[key][member], nil
}
func (m *mockRedis) HIncrByFloat(_ context.Context, key, field string, incr float64) error {
	if m.hash[key] == nil {
		m.hash[key] = make(map[string]string)
	}
	var cur float64
	if v, ok := m.hash[key][field]; ok {
		fmt.Sscanf(v, "%f", &cur)
	}
	m.hash[key][field] = fmt.Sprintf("%f", cur+incr)
	return nil
}
func (m *mockRedis) HGetAll(_ context.Context, key string) (map[string]string, error) {
	if m.hash[key] == nil {
		return nil, nil
	}
	return m.hash[key], nil
}
func (m *mockRedis) Expire(_ context.Context, _ string, _ time.Duration) error { return nil }

type mockProfileStore struct {
	profiles map[string]*UserHolisticProfile
}
func (m *mockProfileStore) GetProfile(_ context.Context, userID string) (*UserHolisticProfile, error) {
	return m.profiles[userID], nil
}

func TestPageContextManager_ReportAndGet(t *testing.T) {
	redis := newMockRedis()
	mgr := NewPageContextManager(redis, nil)
	ctx := context.Background()

	req := PageContextRequest{
		UserID:    "u1",
		SessionID: "s1",
		PageType:  PageContentDetail,
		Objects: PageObjects{
			Post: &PostSnapshot{
				ID: "p1", ContentType: "article", Title: "Test Post",
				Tags: []string{"travel", "food"}, Author: UserBrief{UserID: "a1"},
			},
		},
		UserAction: "viewing",
	}

	if err := mgr.Report(ctx, req); err != nil {
		t.Fatalf("Report: %v", err)
	}

	snap, err := mgr.Get(ctx, "u1")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if snap == nil {
		t.Fatal("expected snapshot, got nil")
	}
	if snap.PageType != PageContentDetail {
		t.Errorf("pageType: got %q, want %q", snap.PageType, PageContentDetail)
	}
	if snap.Objects.Post.ID != "p1" {
		t.Errorf("post ID: got %q, want %q", snap.Objects.Post.ID, "p1")
	}
}

func TestPageContextManager_Clear(t *testing.T) {
	redis := newMockRedis()
	mgr := NewPageContextManager(redis, nil)
	ctx := context.Background()

	mgr.Report(ctx, PageContextRequest{
		UserID: "u1", SessionID: "s1", PageType: PageFeed,
	})

	mgr.Clear(ctx, "u1")

	snap, _ := mgr.Get(ctx, "u1")
	if snap != nil {
		t.Error("expected nil after clear")
	}
}

func TestPageContextManager_ForwardsUserActionsToHotPath(t *testing.T) {
	redis := newMockRedis()
	hp := recommendation.NewHotPath(redis)
	mgr := NewPageContextManager(redis, hp)
	ctx := context.Background()

	req := PageContextRequest{
		UserID:    "u1",
		SessionID: "s1",
		PageType:  PageContentDetail,
		Objects: PageObjects{
			Post: &PostSnapshot{
				ID: "p1", Tags: []string{"travel"},
			},
		},
		UserActions: []UserActionEvent{
			{Action: "like", ObjectID: "p1", Timestamp: time.Now()},
		},
	}

	if err := mgr.Report(ctx, req); err != nil {
		t.Fatalf("Report: %v", err)
	}

	// Verify hot path received the signal via the exposed set
	exposed, _ := hp.IsExposed(ctx, "u1", "", "p1")
	if !exposed {
		t.Error("p1 should be in exposed set after user action forwarding")
	}
}

func TestContextAssembler_Assemble(t *testing.T) {
	redis := newMockRedis()
	hp := recommendation.NewHotPath(redis)
	mgr := NewPageContextManager(redis, hp)
	ctx := context.Background()

	mgr.Report(ctx, PageContextRequest{
		UserID: "u1", SessionID: "s1", PageType: PageContentDetail,
		Objects: PageObjects{Post: &PostSnapshot{ID: "p1", Title: "Hello"}},
	})

	profiles := &mockProfileStore{
		profiles: map[string]*UserHolisticProfile{
			"u1": {
				UserID: "u1",
				ContentPreference: ProfileDimension{
					Tags: map[string]float64{"travel": 5.0, "food": 3.0},
				},
			},
		},
	}

	assembler := NewContextAssembler(mgr, hp, profiles, nil)
	result, err := assembler.Assemble(ctx, "u1", "s1")
	if err != nil {
		t.Fatalf("Assemble: %v", err)
	}
	if result.PageContext == nil {
		t.Error("PageContext should not be nil")
	}
	if result.HolisticProfile == nil {
		t.Error("HolisticProfile should not be nil")
	}
	if result.HolisticProfile.ContentPreference.Tags["travel"] != 5.0 {
		t.Errorf("travel tag: got %v, want 5.0", result.HolisticProfile.ContentPreference.Tags["travel"])
	}
}

func TestContextAssembler_NoData(t *testing.T) {
	redis := newMockRedis()
	hp := recommendation.NewHotPath(redis)
	mgr := NewPageContextManager(redis, hp)

	assembler := NewContextAssembler(mgr, hp, &mockProfileStore{profiles: map[string]*UserHolisticProfile{}}, nil)
	result, err := assembler.Assemble(context.Background(), "unknown", "s1")
	if err != nil {
		t.Fatalf("Assemble: %v", err)
	}
	if result.PageContext != nil {
		t.Error("PageContext should be nil for unknown user")
	}
	if result.HolisticProfile != nil {
		t.Error("HolisticProfile should be nil for unknown user")
	}
}
