package application

import (
	"context"
	"errors"
	"strings"
	"testing"

	rterr "quwoquan_service/runtime/errors"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/infrastructure/persistence"
)

// TestSkillConsentFailClosedEverywhere 锁定 R-CLOUD02 的三个 fail-closed 面：
// store 未装配、store 查询失败、creationAssistantEnabled 不因错误放行。
func TestSkillConsentFailClosedEverywhere(t *testing.T) {
	t.Parallel()
	ctx := context.Background()

	// 1. store 未装配：敏感技能执行点拒绝。
	noStore := NewAssistantService(
		persistence.NewMemoryEventStore(),
		nil,
		rtredis.NewMemoryClient(),
		WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
	)
	if err := noStore.requireSkillConsent(ctx, "user-a", SkillPersonalContentAccess); err == nil {
		t.Fatal("missing consent store must fail closed")
	}
	// creationAssistantEnabled 不因双 store 缺失放行。
	if noStore.creationAssistantEnabled(ctx, "user-a") {
		t.Fatal("creationAssistantEnabled must not open when stores are missing")
	}

	// 2. 未授权：拒绝并携带 skill_consent_required 错误码。
	withStore := NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
	)
	err := withStore.requireSkillConsent(ctx, "user-a", SkillPersonalContentAccess)
	var appErr *rterr.AppError
	if !errors.As(err, &appErr) || !strings.Contains(appErr.Code.String(), "skill_consent_required") {
		t.Fatalf("ungranted skill must return skill_consent_required, got %v", err)
	}

	// 3. 授权后放行；撤权后立即拒绝。
	if _, err := withStore.GrantSkillConsent(ctx, "user-a", SkillPersonalContentAccess, SkillPersonalContentAccess); err != nil {
		t.Fatalf("grant consent: %v", err)
	}
	if err := withStore.requireSkillConsent(ctx, "user-a", SkillPersonalContentAccess); err != nil {
		t.Fatalf("granted skill must pass gate: %v", err)
	}
	if err := withStore.RevokeSkillConsent(ctx, "user-a", SkillPersonalContentAccess); err != nil {
		t.Fatalf("revoke consent: %v", err)
	}
	if err := withStore.requireSkillConsent(ctx, "user-a", SkillPersonalContentAccess); err == nil {
		t.Fatal("revoked skill must fail closed immediately")
	}

	// 4. 非敏感技能不受影响。
	if err := withStore.requireSkillConsent(ctx, "user-a", "news_briefing"); err != nil {
		t.Fatalf("non-consent skill must not be gated: %v", err)
	}
}

// TestConsentGateEnforcedInAgentLoop 验证执行点兜底 gate：
// 敏感技能 turn 在未授权时（绕过创建点直接写入）流式执行被拒绝。
func TestConsentGateEnforcedInAgentLoop(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	store := persistence.NewMemoryConversationRunStore()
	service := NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		WithConversationRunStore(store),
	)

	// 直接经 store 注入一条敏感技能 running turn（模拟绕过创建点的路径）。
	turn := assistant.AssistantTurn{
		TurnID:         "turn-consent-gate",
		ConversationID: "conv-consent-gate",
		UserID:         "user-gate",
		TurnType:       "user",
		Status:         "running",
		SkillID:        SkillPersonalContentAccess,
		Input:          assistant.AssistantTurnInput{Text: "读我的个人内容"},
	}
	if _, _, err := store.InsertTurn(ctx, turn); err != nil {
		t.Fatalf("seed turn: %v", err)
	}
	_, err := service.ExecuteTurn(ctx, "user-gate", "turn-consent-gate")
	var appErr *rterr.AppError
	if !errors.As(err, &appErr) || !strings.Contains(appErr.Code.String(), "skill_consent_required") {
		t.Fatalf("execution-point gate must deny ungranted sensitive skill, got %v", err)
	}
}
