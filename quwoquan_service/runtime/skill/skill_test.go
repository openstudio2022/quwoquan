package skill

import (
	"context"
	"testing"
	"time"

	rctx "quwoquan_service/runtime/context"
)

// testSkill is a simple test skill.
type testSkill struct {
	manifest SkillManifest
	output   SkillOutput
}

func (s *testSkill) Manifest() SkillManifest { return s.manifest }
func (s *testSkill) Execute(_ context.Context, _ SkillInput) (SkillOutput, error) {
	return s.output, nil
}

func travelSkill() *testSkill {
	return &testSkill{
		manifest: SkillManifest{
			ID: "travel_planner", Name: "出行规划", Provider: "internal", Version: "1.0",
			ApplicablePages: []PageMatcher{
				{PageType: "content_detail", ContentTypes: []string{"article", "image"}, TagMatch: []string{"travel"}},
			},
			ContextRequirements: ContextScope{Page: true, Profile: true},
			ToolDependencies:    []string{"content.search"},
			DataClassMax:        DataClassPII,
			RequiresConsent:     true,
			Priority:            10,
		},
		output: SkillOutput{Type: "structured", Content: "出行规划建议"},
	}
}

func foodSkill() *testSkill {
	return &testSkill{
		manifest: SkillManifest{
			ID: "food_recommend", Name: "美食推荐", Provider: "internal", Version: "1.0",
			ApplicablePages: []PageMatcher{
				{PageType: "content_detail", TagMatch: []string{"food"}},
			},
			DataClassMax: DataClassPublic,
			Priority:     5,
		},
		output: SkillOutput{Type: "text", Content: "推荐美食"},
	}
}

func TestRouter_MatchByPageAndTag(t *testing.T) {
	router := NewRouter()
	router.Register(travelSkill(), foodSkill())

	pageCtx := &rctx.PageContextSnapshot{
		PageType: rctx.PageContentDetail,
		Objects: rctx.PageObjects{
			Post: &rctx.PostSnapshot{
				ID: "p1", ContentType: "article", Tags: []string{"travel", "japan"},
			},
		},
	}

	matched := router.Match(pageCtx)
	if len(matched) != 1 {
		t.Fatalf("expected 1 match, got %d", len(matched))
	}
	if matched[0].Manifest().ID != "travel_planner" {
		t.Errorf("expected travel_planner, got %s", matched[0].Manifest().ID)
	}
}

func TestRouter_MatchMultiple_SortedByPriority(t *testing.T) {
	router := NewRouter()
	router.Register(travelSkill(), foodSkill())

	pageCtx := &rctx.PageContextSnapshot{
		PageType: rctx.PageContentDetail,
		Objects: rctx.PageObjects{
			Post: &rctx.PostSnapshot{
				ID: "p1", ContentType: "article", Tags: []string{"travel", "food"},
			},
		},
	}

	matched := router.Match(pageCtx)
	if len(matched) != 2 {
		t.Fatalf("expected 2 matches, got %d", len(matched))
	}
	if matched[0].Manifest().ID != "travel_planner" {
		t.Errorf("first should be travel_planner (priority 10), got %s", matched[0].Manifest().ID)
	}
	if matched[1].Manifest().ID != "food_recommend" {
		t.Errorf("second should be food_recommend (priority 5), got %s", matched[1].Manifest().ID)
	}
}

func TestRouter_NoMatch(t *testing.T) {
	router := NewRouter()
	router.Register(travelSkill())

	pageCtx := &rctx.PageContextSnapshot{
		PageType: rctx.PageChat,
	}

	matched := router.Match(pageCtx)
	if len(matched) != 0 {
		t.Errorf("expected 0 matches for chat page, got %d", len(matched))
	}
}

func TestToolRegistry_RegisterAndCall(t *testing.T) {
	reg := NewToolRegistry()
	reg.RegisterTool(
		Tool{ID: "content.search", Name: "内容搜索", DataClassMax: DataClassPublic},
		func(_ context.Context, input map[string]any) (map[string]any, error) {
			return map[string]any{"results": []string{"r1", "r2"}}, nil
		},
	)

	tool, ok := reg.GetTool("content.search")
	if !ok {
		t.Fatal("tool not found")
	}
	if tool.Name != "内容搜索" {
		t.Errorf("unexpected name: %s", tool.Name)
	}

	result, err := reg.Call(context.Background(), "content.search", map[string]any{"query": "travel"})
	if err != nil {
		t.Fatalf("Call: %v", err)
	}
	if result["results"] == nil {
		t.Error("expected results in output")
	}
}

func TestGuardedToolProxy_DataClassDenied(t *testing.T) {
	reg := NewToolRegistry()
	reg.RegisterTool(
		Tool{ID: "user.private", Name: "私密数据", DataClassMax: DataClassSensitive},
		func(_ context.Context, _ map[string]any) (map[string]any, error) {
			return map[string]any{}, nil
		},
	)

	proxy := &guardedToolProxy{
		registry:     reg,
		dataClassMax: DataClassPublic,
	}

	_, err := proxy.Call(context.Background(), "user.private", nil)
	if err == nil {
		t.Fatal("expected error for data class violation")
	}
}

func TestGuardedToolProxy_DataClassAllowed(t *testing.T) {
	reg := NewToolRegistry()
	reg.RegisterTool(
		Tool{ID: "content.search", Name: "搜索", DataClassMax: DataClassPublic},
		func(_ context.Context, _ map[string]any) (map[string]any, error) {
			return map[string]any{"ok": true}, nil
		},
	)

	proxy := &guardedToolProxy{
		registry:     reg,
		dataClassMax: DataClassPII,
	}

	result, err := proxy.Call(context.Background(), "content.search", nil)
	if err != nil {
		t.Fatalf("Call: %v", err)
	}
	if result["ok"] != true {
		t.Error("expected ok=true")
	}
}

type mockConsentStore struct {
	consents map[string]bool
}

func (m *mockConsentStore) HasConsent(_ context.Context, userID, skillID string) (bool, error) {
	return m.consents[userID+":"+skillID], nil
}
func (m *mockConsentStore) GrantConsent(_ context.Context, record ConsentRecord) error {
	m.consents[record.UserID+":"+record.SkillID] = true
	return nil
}
func (m *mockConsentStore) RevokeConsent(_ context.Context, userID, skillID string) error {
	delete(m.consents, userID+":"+skillID)
	return nil
}

func TestExecutor_ConsentRequired(t *testing.T) {
	router := NewRouter()
	router.Register(travelSkill())

	consents := &mockConsentStore{consents: map[string]bool{}}

	executor := NewExecutor(router, consents, nil, nil)
	_, err := executor.Execute(context.Background(), "travel_planner", "u1", "s1", nil)
	if err != ErrConsentRequired {
		t.Errorf("expected ErrConsentRequired, got %v", err)
	}
}

func TestExecutor_ConsentGranted(t *testing.T) {
	router := NewRouter()
	router.Register(travelSkill())

	consents := &mockConsentStore{consents: map[string]bool{"u1:travel_planner": true}}

	executor := NewExecutor(router, consents, nil, nil)
	out, err := executor.Execute(context.Background(), "travel_planner", "u1", "s1", nil)
	if err != nil {
		t.Fatalf("Execute: %v", err)
	}
	if out.Content != "出行规划建议" {
		t.Errorf("unexpected output: %s", out.Content)
	}
}

func TestExecutor_SkillNotFound(t *testing.T) {
	router := NewRouter()
	executor := NewExecutor(router, nil, nil, nil)
	_, err := executor.Execute(context.Background(), "nonexistent", "u1", "s1", nil)
	if err != ErrSkillNotFound {
		t.Errorf("expected ErrSkillNotFound, got %v", err)
	}
}

type slowSkill struct{}

func (s *slowSkill) Manifest() SkillManifest {
	return SkillManifest{ID: "slow", ApplicablePages: []PageMatcher{{PageType: "feed"}}}
}
func (s *slowSkill) Execute(ctx context.Context, _ SkillInput) (SkillOutput, error) {
	select {
	case <-ctx.Done():
		return SkillOutput{}, ctx.Err()
	case <-time.After(30 * time.Second):
		return SkillOutput{Content: "done"}, nil
	}
}

func TestExecutor_Timeout(t *testing.T) {
	router := NewRouter()
	router.Register(&slowSkill{})

	executor := NewExecutor(router, nil, nil, nil)
	executor.timeout = 50 * time.Millisecond

	_, err := executor.Execute(context.Background(), "slow", "u1", "s1", nil)
	if err != ErrSkillTimeout {
		t.Errorf("expected ErrSkillTimeout, got %v", err)
	}
}
