// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"sync"
	"testing"
	"time"

	catalogmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/domain/model"
)

const testSchemaDigest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

type settingStore struct {
	mu      sync.Mutex
	setting *model.Setting
}

func (store *settingStore) Get(
	_ context.Context,
	accountID string,
	skillID string,
) (model.Setting, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.setting == nil || store.setting.AccountID != accountID || store.setting.SkillID != skillID {
		return model.Setting{}, model.ErrNotFound
	}
	return *store.setting, nil
}

func (store *settingStore) List(
	_ context.Context,
	accountID string,
	limit int,
) ([]model.Setting, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.setting == nil || store.setting.AccountID != accountID || limit <= 0 {
		return []model.Setting{}, nil
	}
	return []model.Setting{*store.setting}, nil
}

func (store *settingStore) Apply(
	_ context.Context,
	command model.Command,
) (model.MutationResult, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.setting == nil {
		if command.ExpectedRevision != 0 {
			return model.MutationResult{}, model.ErrRevisionConflict
		}
		store.setting = &model.Setting{
			ID:                        "setting-1",
			AccountID:                 command.AccountID,
			SkillID:                   command.SkillID,
			Status:                    command.Status,
			ConfigurationData:         command.ConfigurationData,
			ConfigurationSchemaDigest: command.ConfigurationSchemaDigest,
			MemoryPolicy:              command.MemoryPolicy,
			ConnectorConnectionRefs:   command.ConnectorConnectionRefs,
			Revision:                  1,
			CreatedAt:                 command.OccurredAt,
			UpdatedAt:                 command.OccurredAt,
		}
		return model.MutationResult{Setting: *store.setting, Changed: true}, nil
	}
	if store.setting.Revision != command.ExpectedRevision {
		return model.MutationResult{}, model.ErrRevisionConflict
	}
	store.setting.Status = command.Status
	store.setting.ConfigurationData = command.ConfigurationData
	store.setting.ConfigurationSchemaDigest = command.ConfigurationSchemaDigest
	store.setting.MemoryPolicy = command.MemoryPolicy
	store.setting.ConnectorConnectionRefs = command.ConnectorConnectionRefs
	store.setting.Revision++
	store.setting.UpdatedAt = command.OccurredAt
	return model.MutationResult{Setting: *store.setting, Changed: true}, nil
}

type settingValidator struct {
	err error
}

func (validator settingValidator) ValidateConfiguration(
	_ context.Context,
	_ string,
	_ string,
	_ json.RawMessage,
) error {
	return validator.err
}

func TestSkillUserSettingDefaultAndExplicitDisableAreIndependent(t *testing.T) {
	t.Parallel()
	store := &settingStore{}
	queries := application.NewQueryFacade(store)
	now := time.Date(2026, 8, 2, 9, 0, 0, 0, time.UTC)
	commands := application.NewCommandFacade(
		store,
		settingValidator{},
		func() time.Time { return now },
	)

	enabled, err := queries.IsEnabled(context.Background(), "account-a", "travel_companion")
	if err != nil || !enabled {
		t.Fatalf("package default enabled=%v error=%v", enabled, err)
	}
	result, err := commands.Put(context.Background(), model.PutInput{
		AccountID:                 "account-a",
		SkillID:                   "travel_companion",
		Status:                    model.StatusDisabled,
		ConfigurationData:         json.RawMessage(`{}`),
		ConfigurationSchemaDigest: testSchemaDigest,
		MemoryPolicy:              model.MemoryConfirmBeforeSave,
		ConnectorConnectionRefs:   []string{"connector-calendar-a"},
		ExpectedRevision:          0,
		IdempotencyKey:            "setting-command-1",
	})
	if err != nil || !result.Changed || result.Setting.Revision != 1 {
		t.Fatalf("Put() result=%+v error=%v", result, err)
	}
	enabled, err = queries.IsEnabled(context.Background(), "account-a", "travel_companion")
	if err != nil || enabled {
		t.Fatalf("explicit disabled enabled=%v error=%v", enabled, err)
	}
	if result.Setting.MemoryPolicy != model.MemoryConfirmBeforeSave ||
		len(result.Setting.ConnectorConnectionRefs) != 1 {
		t.Fatalf("setting lost independent policy fields: %+v", result.Setting)
	}
	settings, err := queries.List(context.Background(), "account-a", 64)
	if err != nil || len(settings) != 1 || settings[0].SkillID != "travel_companion" {
		t.Fatalf("List() explicit settings=%+v error=%v", settings, err)
	}
	defaults, err := queries.List(context.Background(), "account-without-settings", 64)
	if err != nil || len(defaults) != 0 {
		t.Fatalf("List() materialized package defaults=%+v error=%v", defaults, err)
	}
}

func TestSkillUserSettingFailsClosedForPackageAndCAS(t *testing.T) {
	t.Parallel()
	store := &settingStore{}
	input := model.PutInput{
		AccountID:                 "account-a",
		SkillID:                   "travel_companion",
		Status:                    model.StatusEnabled,
		ConfigurationData:         json.RawMessage(`{}`),
		ConfigurationSchemaDigest: testSchemaDigest,
		MemoryPolicy:              model.MemoryPackageDefault,
		ConnectorConnectionRefs:   []string{},
		ExpectedRevision:          0,
		IdempotencyKey:            "setting-command-1",
	}
	withoutPackage := application.NewCommandFacade(store, nil, nil)
	if _, err := withoutPackage.Put(context.Background(), input); !errors.Is(err, model.ErrPackageUnavailable) {
		t.Fatalf("nil package validator error=%v", err)
	}
	mismatch := application.NewCommandFacade(
		store,
		settingValidator{err: catalogmodel.ErrConfigurationSchemaDigestMismatch},
		nil,
	)
	if _, err := mismatch.Put(context.Background(), input); !errors.Is(err, model.ErrSchemaMismatch) {
		t.Fatalf("schema mismatch error=%v", err)
	}
	valid := application.NewCommandFacade(store, settingValidator{}, nil)
	if _, err := valid.Put(context.Background(), input); err != nil {
		t.Fatal(err)
	}
	input.ExpectedRevision = 0
	input.IdempotencyKey = "setting-command-stale"
	if _, err := valid.Put(context.Background(), input); !errors.Is(err, model.ErrRevisionConflict) {
		t.Fatalf("stale CAS error=%v", err)
	}
}
