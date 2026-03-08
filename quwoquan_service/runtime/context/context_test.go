package runtimecontext

import (
	"context"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/recommendation"
)

type mockProfileStore struct {
	profiles map[string]*UserHolisticProfile
}
func (m *mockProfileStore) GetProfile(_ context.Context, userID string) (*UserHolisticProfile, error) {
	return m.profiles[userID], nil
}

func TestPageContextManager_ReportAndGet(t *testing.T) {
	memClient := rtredis.NewMemoryClient()
	mgr := NewPageContextManager(memClient, nil)
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
	memClient := rtredis.NewMemoryClient()
	mgr := NewPageContextManager(memClient, nil)
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
	memClient := rtredis.NewMemoryClient()
	hp := recommendation.NewHotPath(rtredis.NewRecAdapter(memClient))
	mgr := NewPageContextManager(memClient, hp)
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
	memClient := rtredis.NewMemoryClient()
	hp := recommendation.NewHotPath(rtredis.NewRecAdapter(memClient))
	mgr := NewPageContextManager(memClient, hp)
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
	memClient := rtredis.NewMemoryClient()
	hp := recommendation.NewHotPath(rtredis.NewRecAdapter(memClient))
	mgr := NewPageContextManager(memClient, hp)

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
