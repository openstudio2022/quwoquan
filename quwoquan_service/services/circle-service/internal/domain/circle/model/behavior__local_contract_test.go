package circle

import (
	"errors"
	"strings"
	"testing"
	"time"
)

func TestCircleGovernanceTextLifecycle(t *testing.T) {
	now := time.Date(2026, 7, 21, 0, 0, 0, 0, time.UTC)
	name := "摄影同好圈"
	rules := "  尊重原创，禁止人身攻击。  "
	welcome := "  欢迎先阅读圈规，再发布第一条作品。  "
	created, err := Apply(nil, ChangeSet{
		Kind: ChangeCreate, CircleID: "circle-governance",
		OwnerPersonaID: "persona-owner", Name: &name,
		RulesText: &rules, WelcomeMessage: &welcome, OccurredAt: now,
	})
	if err != nil {
		t.Fatalf("create circle governance text: %v", err)
	}
	if created.RulesText != "尊重原创，禁止人身攻击。" {
		t.Fatalf("rulesText not normalized: %q", created.RulesText)
	}
	if created.WelcomeMessage != "欢迎先阅读圈规，再发布第一条作品。" {
		t.Fatalf("welcomeMessage not normalized: %q", created.WelcomeMessage)
	}

	nextRules := "仅发布与摄影相关的内容。"
	nextWelcome := ""
	updated, err := Apply(&created, ChangeSet{
		Kind: ChangeUpdate, CircleID: created.ID,
		ExpectedVersion: created.Version, RulesText: &nextRules,
		WelcomeMessage: &nextWelcome, OccurredAt: now.Add(time.Minute),
	})
	if err != nil {
		t.Fatalf("update circle governance text: %v", err)
	}
	if updated.RulesText != nextRules || updated.WelcomeMessage != "" {
		t.Fatalf("governance text update drift: %+v", updated)
	}
	if updated.Version != created.Version+1 {
		t.Fatalf("version not advanced: before=%d after=%d", created.Version, updated.Version)
	}
}

func TestCircleGovernanceTextRejectsOversizeInput(t *testing.T) {
	now := time.Date(2026, 7, 21, 0, 0, 0, 0, time.UTC)
	name := "超长圈规测试"
	oversizeRules := strings.Repeat("规", maxCircleRulesRunes+1)
	if _, err := Apply(nil, ChangeSet{
		Kind: ChangeCreate, CircleID: "circle-rules-oversize",
		OwnerPersonaID: "persona-owner", Name: &name,
		RulesText: &oversizeRules, OccurredAt: now,
	}); !errors.Is(err, ErrInvalidChange) {
		t.Fatalf("oversize rules must fail closed, got %v", err)
	}

	valid, err := Apply(nil, ChangeSet{
		Kind: ChangeCreate, CircleID: "circle-welcome-oversize",
		OwnerPersonaID: "persona-owner", Name: &name, OccurredAt: now,
	})
	if err != nil {
		t.Fatalf("create valid circle: %v", err)
	}
	oversizeWelcome := strings.Repeat("迎", maxCircleWelcomeRunes+1)
	if _, err := Apply(&valid, ChangeSet{
		Kind: ChangeUpdate, CircleID: valid.ID,
		ExpectedVersion: valid.Version, WelcomeMessage: &oversizeWelcome,
		OccurredAt: now.Add(time.Minute),
	}); !errors.Is(err, ErrInvalidChange) {
		t.Fatalf("oversize welcomeMessage must fail closed, got %v", err)
	}
}
