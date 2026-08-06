// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/session-preference-memory-control/spec.md#gwt-002
// readiness_case: set-assistant-preference-local
// readiness_case: list-assistant-preferences-local
// readiness_case: revoke-assistant-preference-local
// readiness_case: restore-assistant-preference-local
package local_contract

import (
	"context"
	"errors"
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/application"
	"strings"
	"sync"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	preferenceports "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/ports"
)

type assistantPreferenceMemoryStore struct {
	mu          sync.Mutex
	preferences map[string]preferencemodel.AssistantPreference
}

func newAssistantPreferenceMemoryStore() *assistantPreferenceMemoryStore {
	return &assistantPreferenceMemoryStore{preferences: map[string]preferencemodel.AssistantPreference{}}
}

func (s *assistantPreferenceMemoryStore) Upsert(
	_ context.Context,
	input preferenceports.UpsertInput,
) (preferencemodel.AssistantPreference, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for id, current := range s.preferences {
		if current.UserID == input.UserID &&
			current.Scope == input.Scope &&
			current.SessionID == input.SessionID &&
			current.Kind == input.Kind {
			current.Value = input.Value
			current.SourceType = input.SourceType
			current.SourceSessionID = input.SourceSessionID
			current.ConfirmedAt = input.ConfirmedAt
			current.Status = preferencemodel.StatusActive
			current.RevokedAt = nil
			current.RevocationDeadline = nil
			current.UpdatedAt = input.Now
			current.Version++
			s.preferences[id] = current
			return current, nil
		}
	}
	preference := preferencemodel.AssistantPreference{
		PreferenceID:    input.PreferenceID,
		UserID:          input.UserID,
		Scope:           input.Scope,
		SessionID:       input.SessionID,
		Kind:            input.Kind,
		Value:           input.Value,
		SourceType:      input.SourceType,
		SourceSessionID: input.SourceSessionID,
		ConfirmedAt:     input.ConfirmedAt,
		Status:          preferencemodel.StatusActive,
		CreatedAt:       input.Now,
		UpdatedAt:       input.Now,
		Version:         1,
	}
	s.preferences[preference.PreferenceID] = preference
	return preference, nil
}

func (s *assistantPreferenceMemoryStore) List(
	_ context.Context,
	userID string,
	filter preferenceports.ListFilter,
) ([]preferencemodel.AssistantPreference, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	items := []preferencemodel.AssistantPreference{}
	for _, preference := range s.preferences {
		if preference.UserID != userID || preference.Status != filter.Status {
			continue
		}
		if filter.Scope != "" && preference.Scope != filter.Scope {
			continue
		}
		if filter.SessionID != "" &&
			preference.SessionID != filter.SessionID {
			continue
		}
		items = append(items, preference)
	}
	return items, nil
}

func (s *assistantPreferenceMemoryStore) ListActiveForRun(
	_ context.Context,
	userID string,
	sessionID string,
	limitPerScope int,
) ([]preferencemodel.AssistantPreference, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	items := []preferencemodel.AssistantPreference{}
	sessionCount := 0
	longTermCount := 0
	for _, preference := range s.preferences {
		if preference.UserID != userID || preference.Status != preferencemodel.StatusActive {
			continue
		}
		switch preference.Scope {
		case preferencemodel.ScopeSession:
			if preference.SessionID != sessionID ||
				sessionCount >= limitPerScope {
				continue
			}
			sessionCount++
		case preferencemodel.ScopeLongTerm:
			if longTermCount >= limitPerScope {
				continue
			}
			longTermCount++
		default:
			continue
		}
		items = append(items, preference)
	}
	return items, nil
}

func (s *assistantPreferenceMemoryStore) GetOwned(
	_ context.Context,
	userID string,
	preferenceID string,
) (preferencemodel.AssistantPreference, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	preference, ok := s.preferences[preferenceID]
	if !ok || preference.UserID != userID {
		return preferencemodel.AssistantPreference{}, false, nil
	}
	return preference, true, nil
}

func (s *assistantPreferenceMemoryStore) UpdateStatus(
	_ context.Context,
	userID string,
	preferenceID string,
	expectedVersion int64,
	update preferenceports.StatusUpdate,
) (preferencemodel.AssistantPreference, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	preference, ok := s.preferences[preferenceID]
	if !ok || preference.UserID != userID || preference.Version != expectedVersion {
		return preferencemodel.AssistantPreference{}, false, nil
	}
	preference.Status = update.Status
	preference.RevokedAt = update.RevokedAt
	preference.RevocationDeadline = update.RevocationDeadline
	preference.UpdatedAt = update.UpdatedAt
	preference.Version++
	s.preferences[preferenceID] = preference
	return preference, true, nil
}

type assistantPreferenceOwnedSessionReader struct {
	userID    string
	sessionID string
}

func (r assistantPreferenceOwnedSessionReader) OwnedSessionExists(
	_ context.Context,
	userID string,
	sessionID string,
) (bool, error) {
	return userID == r.userID && sessionID == r.sessionID, nil
}

func TestAssistantPreferenceSessionLifecycleAndOwnerIsolation(t *testing.T) {
	store := newAssistantPreferenceMemoryStore()
	commands := NewCommandFacade(
		store,
		assistantPreferenceOwnedSessionReader{
			userID:    "persona-owner",
			sessionID: "asn_owned",
		},
	)
	queries := NewQueryFacade(store)

	if _, err := commands.SetPreference(t.Context(), SetPreferenceCommand{
		UserID:     "another-persona",
		Scope:      "session",
		SessionID:  "asn_owned",
		Kind:       "reply_length",
		Value:      "concise",
		SourceType: "explicit_rewrite",
	}); err == nil {
		t.Fatal("non-owner session preference set must fail")
	} else {
		var appErr *rterr.AppError
		if !errors.As(err, &appErr) ||
			!strings.Contains(appErr.Code.String(), "preference_not_found") {
			t.Fatalf("non-owner set error = %v", err)
		}
	}

	preference, err := commands.SetPreference(t.Context(), SetPreferenceCommand{
		UserID:     "persona-owner",
		Scope:      "session",
		SessionID:  "asn_owned",
		Kind:       "reply_length",
		Value:      "concise",
		SourceType: "explicit_rewrite",
	})
	if err != nil {
		t.Fatalf("SetPreference() error = %v", err)
	}
	if preference.Status != preferencemodel.StatusActive || preference.Version != 1 {
		t.Fatalf("preference = %#v", preference)
	}

	view, err := queries.ListPreferences(t.Context(), ListPreferencesQuery{
		UserID:    "persona-owner",
		Scope:     "session",
		SessionID: "asn_owned",
	})
	if err != nil || len(view.Items) != 1 {
		t.Fatalf("ListPreferences() view=%#v err=%v", view, err)
	}

	revoked, err := commands.RevokePreference(
		t.Context(),
		"persona-owner",
		preference.PreferenceID,
	)
	if err != nil {
		t.Fatalf("RevokePreference() error = %v", err)
	}
	if revoked.Status != preferencemodel.StatusRevoked ||
		revoked.RevocationDeadline == nil {
		t.Fatalf("revoked = %#v", revoked)
	}
	activeAfterRevoke, err := queries.ListPreferences(t.Context(), ListPreferencesQuery{
		UserID:    "persona-owner",
		Scope:     "session",
		SessionID: "asn_owned",
	})
	if err != nil || len(activeAfterRevoke.Items) != 0 {
		t.Fatalf(
			"revoked preference remained in active list=%#v err=%v",
			activeAfterRevoke,
			err,
		)
	}
	sessionAfterRevoke, _, err := queries.ResolveActiveSnapshots(
		t.Context(),
		"persona-owner",
		"asn_owned",
	)
	if err != nil || len(sessionAfterRevoke) != 0 {
		t.Fatalf(
			"revoked preference remained in run snapshots=%#v err=%v",
			sessionAfterRevoke,
			err,
		)
	}

	if _, err := commands.RestorePreference(
		t.Context(),
		"another-persona",
		preference.PreferenceID,
	); err == nil {
		t.Fatal("non-owner restore must fail")
	} else {
		var appErr *rterr.AppError
		if !errors.As(err, &appErr) ||
			!strings.Contains(appErr.Code.String(), "preference_not_found") {
			t.Fatalf("non-owner error = %v", err)
		}
	}

	restored, err := commands.RestorePreference(
		t.Context(),
		"persona-owner",
		preference.PreferenceID,
	)
	if err != nil {
		t.Fatalf("RestorePreference() error = %v", err)
	}
	if restored.Status != preferencemodel.StatusActive ||
		restored.RevokedAt != nil ||
		restored.RevocationDeadline != nil {
		t.Fatalf("restored = %#v", restored)
	}
	activeAfterRestore, err := queries.ListPreferences(t.Context(), ListPreferencesQuery{
		UserID:    "persona-owner",
		Scope:     "session",
		SessionID: "asn_owned",
	})
	if err != nil || len(activeAfterRestore.Items) != 1 ||
		activeAfterRestore.Items[0].PreferenceID != preference.PreferenceID {
		t.Fatalf(
			"restored preference missing from active list=%#v err=%v",
			activeAfterRestore,
			err,
		)
	}
	sessionAfterRestore, _, err := queries.ResolveActiveSnapshots(
		t.Context(),
		"persona-owner",
		"asn_owned",
	)
	if err != nil || len(sessionAfterRestore) != 1 ||
		sessionAfterRestore[0].PreferenceID != preference.PreferenceID {
		t.Fatalf(
			"restored preference missing from run snapshots=%#v err=%v",
			sessionAfterRestore,
			err,
		)
	}
	for _, operation := range []func(context.Context, string, string) (preferencemodel.AssistantPreference, error){
		commands.RevokePreference,
		commands.RestorePreference,
	} {
		if _, err := operation(t.Context(), "persona-owner", "apf-not-found"); err == nil {
			t.Fatal("missing preference operation must fail")
		} else {
			var appErr *rterr.AppError
			if !errors.As(err, &appErr) ||
				!strings.Contains(appErr.Code.String(), "preference_not_found") {
				t.Fatalf("missing preference error = %v", err)
			}
		}
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/long-term-memory-compaction/spec.md#gwt-001
func TestConfirmedLongTermMemoryRequiresConfirmationAndReusesRevokeRestore(t *testing.T) {
	store := newAssistantPreferenceMemoryStore()
	commands := NewCommandFacade(
		store,
		assistantPreferenceOwnedSessionReader{
			userID:    "persona-memory",
			sessionID: "asn_memory_source",
		},
	)
	queries := NewQueryFacade(store)
	command := SetPreferenceCommand{
		UserID:          "persona-memory",
		Scope:           "long_term",
		Kind:            "dietary_restrictions",
		Value:           "对花生过敏，不吃含花生的食物",
		SourceType:      "session_confirmed",
		SourceSessionID: "asn_memory_source",
	}
	if _, err := commands.SetPreference(t.Context(), command); err == nil {
		t.Fatal("unconfirmed confirmed memory must be rejected")
	}
	command.Confirmed = true
	preference, err := commands.SetPreference(t.Context(), command)
	if err != nil {
		t.Fatalf("SetPreference(confirmed memory): %v", err)
	}
	if preference.Kind != preferencemodel.KindDietaryRestrictions ||
		preference.SourceSessionID != "asn_memory_source" ||
		preference.ConfirmedAt == nil {
		t.Fatalf("confirmed memory attribution=%#v", preference)
	}
	if _, err := commands.RevokePreference(
		t.Context(),
		"another-persona",
		preference.PreferenceID,
	); err == nil {
		t.Fatal("non-owner must not revoke confirmed memory")
	}
	if _, err := commands.RevokePreference(
		t.Context(),
		"persona-memory",
		preference.PreferenceID,
	); err != nil {
		t.Fatalf("RevokePreference(): %v", err)
	}
	_, longTerm, err := queries.ResolveActiveSnapshots(
		t.Context(),
		"persona-memory",
		"asn_new_session",
	)
	if err != nil {
		t.Fatalf("ResolveActiveSnapshots(revoked): %v", err)
	}
	if len(longTerm) != 0 {
		t.Fatalf("revoked confirmed memory remained active: %#v", longTerm)
	}
	if _, err := commands.RestorePreference(
		t.Context(),
		"persona-memory",
		preference.PreferenceID,
	); err != nil {
		t.Fatalf("RestorePreference(): %v", err)
	}
	_, longTerm, err = queries.ResolveActiveSnapshots(
		t.Context(),
		"persona-memory",
		"asn_new_session",
	)
	if err != nil {
		t.Fatalf("ResolveActiveSnapshots(restored): %v", err)
	}
	if len(longTerm) != 1 ||
		longTerm[0].Kind != preferencemodel.KindDietaryRestrictions ||
		longTerm[0].SourceSessionID != "asn_memory_source" {
		t.Fatalf("restored confirmed memory snapshots=%#v", longTerm)
	}
}

func TestAssistantPreferenceRestoreWindowExpiresFailClosed(t *testing.T) {
	store := newAssistantPreferenceMemoryStore()
	commands := NewCommandFacade(store, assistantPreferenceOwnedSessionReader{})

	preference, err := commands.SetPreference(t.Context(), SetPreferenceCommand{
		UserID:     "persona-owner",
		Scope:      "long_term",
		Kind:       "tone",
		Value:      "warm",
		SourceType: "management",
	})
	if err != nil {
		t.Fatalf("SetPreference() error = %v", err)
	}
	if _, err := commands.RevokePreference(
		t.Context(),
		"persona-owner",
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
	if _, err := commands.RestorePreference(
		t.Context(),
		"persona-owner",
		preference.PreferenceID,
	); err == nil {
		t.Fatal("expired restore must fail")
	} else {
		var appErr *rterr.AppError
		if !errors.As(err, &appErr) ||
			!strings.Contains(appErr.Code.String(), "preference_restore_expired") {
			t.Fatalf("expired restore error = %v", err)
		}
	}
}

func TestResolveActiveSnapshotsSeparatesSessionAndLongTerm(t *testing.T) {
	store := newAssistantPreferenceMemoryStore()
	commands := NewCommandFacade(
		store,
		assistantPreferenceOwnedSessionReader{
			userID:    "persona-owner",
			sessionID: "asn_owned",
		},
	)
	for _, command := range []SetPreferenceCommand{
		{
			UserID:     "persona-owner",
			Scope:      "session",
			SessionID:  "asn_owned",
			Kind:       "reply_length",
			Value:      "concise",
			SourceType: "explicit_rewrite",
		},
		{
			UserID:     "persona-owner",
			Scope:      "long_term",
			Kind:       "tone",
			Value:      "professional",
			SourceType: "management",
		},
	} {
		if _, err := commands.SetPreference(t.Context(), command); err != nil {
			t.Fatalf("SetPreference(%#v) error = %v", command, err)
		}
	}
	session, longTerm, err := NewQueryFacade(store).ResolveActiveSnapshots(
		t.Context(),
		"persona-owner",
		"asn_owned",
	)
	if err != nil {
		t.Fatalf("ResolveActiveSnapshots() error = %v", err)
	}
	if len(session) != 1 || session[0].Scope != preferencemodel.ScopeSession {
		t.Fatalf("session = %#v", session)
	}
	if len(longTerm) != 1 ||
		longTerm[0].Scope != preferencemodel.ScopeLongTerm {
		t.Fatalf("longTerm = %#v", longTerm)
	}
}
