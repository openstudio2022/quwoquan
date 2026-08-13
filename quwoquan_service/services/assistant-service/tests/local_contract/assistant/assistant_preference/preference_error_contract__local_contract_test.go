// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/session-preference-memory-control/spec.md#gwt-002
// 错误契约语义双向锁：AssistantPreference errors.yaml 声明的错误码由真实负例触发，
// 并断言 canonical code 与 http_status。
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	preferenceapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/application"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	preferenceports "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/ports"
)

// failingPreferenceStore 是对象级 typed double：所有存储操作均返回注入的失败。
type failingPreferenceStore struct{ err error }

func (store failingPreferenceStore) Upsert(
	context.Context,
	preferenceports.UpsertInput,
) (preferencemodel.AssistantPreference, error) {
	return preferencemodel.AssistantPreference{}, store.err
}

func (store failingPreferenceStore) List(
	context.Context,
	string,
	preferenceports.ListFilter,
) ([]preferencemodel.AssistantPreference, error) {
	return nil, store.err
}

func (store failingPreferenceStore) ListActiveForRun(
	context.Context,
	string,
	string,
	int,
) ([]preferencemodel.AssistantPreference, error) {
	return nil, store.err
}

func (store failingPreferenceStore) GetOwned(
	context.Context,
	string,
	string,
) (preferencemodel.AssistantPreference, bool, error) {
	return preferencemodel.AssistantPreference{}, false, store.err
}

func (store failingPreferenceStore) UpdateStatus(
	context.Context,
	string,
	string,
	int64,
	preferenceports.StatusUpdate,
) (preferencemodel.AssistantPreference, bool, error) {
	return preferencemodel.AssistantPreference{}, false, store.err
}

func assertPreferenceError(t *testing.T, err error, code string, status int) {
	t.Helper()
	var appErr *rterr.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("error=%T %v, want *rterr.AppError", err, err)
	}
	if appErr.Code.String() != code || appErr.HTTPStatus != status {
		t.Fatalf(
			"error=%s/%d, want %s/%d",
			appErr.Code.String(),
			appErr.HTTPStatus,
			code,
			status,
		)
	}
}

func TestAssistantPreferenceCommandsEmitCanonicalErrorContract(t *testing.T) {
	t.Parallel()

	store := newAssistantPreferenceMemoryStore()
	commands := preferenceapplication.NewCommandFacade(
		store,
		assistantPreferenceOwnedSessionReader{
			userID:    "persona-error-owner",
			sessionID: "asn_error_owned",
		},
	)

	_, err := commands.SetPreference(
		t.Context(),
		preferenceapplication.SetPreferenceCommand{
			UserID:     "persona-error-owner",
			Scope:      "long_term",
			Kind:       "not_a_canonical_kind",
			Value:      "warm",
			SourceType: "management",
		},
	)
	assertPreferenceError(
		t,
		err,
		"ASSISTANT.USER.preference_invalid_argument",
		400,
	)

	_, err = commands.RevokePreference(
		t.Context(),
		"persona-error-owner",
		"apf-missing",
	)
	assertPreferenceError(t, err, "ASSISTANT.USER.preference_not_found", 404)

	preference, err := commands.SetPreference(
		t.Context(),
		preferenceapplication.SetPreferenceCommand{
			UserID:     "persona-error-owner",
			Scope:      "long_term",
			Kind:       "tone",
			Value:      "warm",
			SourceType: "management",
		},
	)
	if err != nil {
		t.Fatalf("SetPreference() error = %v", err)
	}
	if _, err := commands.RevokePreference(
		t.Context(),
		"persona-error-owner",
		preference.PreferenceID,
	); err != nil {
		t.Fatalf("RevokePreference() error = %v", err)
	}
	expiredAt := time.Now().UTC().Add(-time.Second)
	store.mu.Lock()
	stored := store.preferences[preference.PreferenceID]
	stored.RevocationDeadline = &expiredAt
	store.preferences[preference.PreferenceID] = stored
	store.mu.Unlock()
	_, err = commands.RestorePreference(
		t.Context(),
		"persona-error-owner",
		preference.PreferenceID,
	)
	assertPreferenceError(
		t,
		err,
		"ASSISTANT.USER.preference_restore_expired",
		409,
	)

	failing := preferenceapplication.NewCommandFacade(
		failingPreferenceStore{err: errors.New("postgres connection refused")},
		assistantPreferenceOwnedSessionReader{},
	)
	_, err = failing.SetPreference(
		t.Context(),
		preferenceapplication.SetPreferenceCommand{
			UserID:     "persona-error-owner",
			Scope:      "long_term",
			Kind:       "tone",
			Value:      "warm",
			SourceType: "management",
		},
	)
	assertPreferenceError(
		t,
		err,
		"ASSISTANT.SYSTEM.preference_storage_unavailable",
		503,
	)
}
