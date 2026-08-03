// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
package api_integration

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/domain/model"
)

type allowConfiguration struct{}

func (allowConfiguration) ValidateConfiguration(context.Context, string, string, json.RawMessage) error {
	return nil
}

func TestSkillUserSettingPostgresCommitsCASReceiptAndOutboxAtomically(t *testing.T) {
	resetSettingState(t)
	now := time.Date(2026, 8, 2, 11, 0, 0, 0, time.UTC)
	commands := application.NewCommandFacade(
		settingStore,
		allowConfiguration{},
		func() time.Time { return now },
	)
	input := model.PutInput{
		AccountID:                 "account-a",
		SkillID:                   "travel_companion",
		Status:                    model.StatusEnabled,
		ConfigurationData:         json.RawMessage(`{}`),
		ConfigurationSchemaDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		MemoryPolicy:              model.MemoryConfirmBeforeSave,
		ConnectorConnectionRefs:   []string{"calendar-a"},
		ExpectedRevision:          0,
		IdempotencyKey:            "setting-command-create",
	}
	created, err := commands.Put(context.Background(), input)
	if err != nil || !created.Changed || created.Setting.Revision != 1 {
		t.Fatalf("create result=%+v error=%v", created, err)
	}
	replayed, err := commands.Put(context.Background(), input)
	if err != nil || !replayed.Replayed || replayed.Setting.ID != created.Setting.ID {
		t.Fatalf("replay result=%+v error=%v", replayed, err)
	}
	input.Status = model.StatusDisabled
	if _, err := commands.Put(context.Background(), input); !errors.Is(err, model.ErrIdempotencyConflict) {
		t.Fatalf("idempotency conflict error=%v", err)
	}
	input.IdempotencyKey = "setting-command-update"
	input.ExpectedRevision = 1
	updated, err := commands.Put(context.Background(), input)
	if err != nil || updated.Setting.Revision != 2 || updated.Setting.Status != model.StatusDisabled {
		t.Fatalf("update result=%+v error=%v", updated, err)
	}
	queries := application.NewQueryFacade(settingStore)
	enabled, err := queries.IsEnabled(context.Background(), "account-a", "travel_companion")
	if err != nil || enabled {
		t.Fatalf("effective enabled=%v error=%v", enabled, err)
	}
	listed, err := queries.List(context.Background(), "account-a", 64)
	if err != nil || len(listed) != 1 || listed[0].Revision != 2 {
		t.Fatalf("list explicit settings=%+v error=%v", listed, err)
	}
	empty, err := queries.List(context.Background(), "account-b", 64)
	if err != nil || len(empty) != 0 {
		t.Fatalf("list default-only account=%+v error=%v", empty, err)
	}
	var settings, receipts, outbox int
	if err := settingPool.QueryRow(context.Background(), `
SELECT
  (SELECT COUNT(*) FROM skill_user_settings),
  (SELECT COUNT(*) FROM skill_user_setting_command_receipts),
  (SELECT COUNT(*) FROM skill_user_setting_outbox)`).Scan(&settings, &receipts, &outbox); err != nil {
		t.Fatal(err)
	}
	if settings != 1 || receipts != 2 || outbox != 2 {
		t.Fatalf("setting/receipt/outbox=%d/%d/%d, want 1/2/2", settings, receipts, outbox)
	}
}
