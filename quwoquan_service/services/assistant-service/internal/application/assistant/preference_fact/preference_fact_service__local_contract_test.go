package preferencefact

import (
	"context"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	preferencemodel "quwoquan_service/services/assistant-service/internal/domain/assistant/preference_fact/model"
	preferenceports "quwoquan_service/services/assistant-service/internal/domain/assistant/preference_fact/ports"
)

type memoryPreferenceStore struct {
	mu    sync.Mutex
	facts map[string]preferencemodel.Fact
}

func newMemoryPreferenceStore() *memoryPreferenceStore {
	return &memoryPreferenceStore{facts: map[string]preferencemodel.Fact{}}
}

func (s *memoryPreferenceStore) Upsert(
	_ context.Context,
	input preferenceports.UpsertInput,
) (preferencemodel.Fact, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for id, current := range s.facts {
		if current.UserID == input.UserID &&
			current.Scope == input.Scope &&
			current.ConversationID == input.ConversationID &&
			current.Kind == input.Kind {
			current.Value = input.Value
			current.SourceType = input.SourceType
			current.Status = preferencemodel.StatusActive
			current.RevokedAt = nil
			current.RevocationDeadline = nil
			current.UpdatedAt = input.Now
			current.Version++
			s.facts[id] = current
			return current, nil
		}
	}
	fact := preferencemodel.Fact{
		PreferenceID:   input.PreferenceID,
		UserID:         input.UserID,
		Scope:          input.Scope,
		ConversationID: input.ConversationID,
		Kind:           input.Kind,
		Value:          input.Value,
		SourceType:     input.SourceType,
		Status:         preferencemodel.StatusActive,
		CreatedAt:      input.Now,
		UpdatedAt:      input.Now,
		Version:        1,
	}
	s.facts[fact.PreferenceID] = fact
	return fact, nil
}

func (s *memoryPreferenceStore) List(
	_ context.Context,
	userID string,
	filter preferenceports.ListFilter,
) ([]preferencemodel.Fact, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	items := []preferencemodel.Fact{}
	for _, fact := range s.facts {
		if fact.UserID != userID || fact.Status != filter.Status {
			continue
		}
		if filter.Scope != "" && fact.Scope != filter.Scope {
			continue
		}
		if filter.ConversationID != "" &&
			fact.ConversationID != filter.ConversationID {
			continue
		}
		items = append(items, fact)
	}
	return items, nil
}

func (s *memoryPreferenceStore) ListActiveForRun(
	_ context.Context,
	userID string,
	conversationID string,
	limitPerScope int,
) ([]preferencemodel.Fact, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	items := []preferencemodel.Fact{}
	sessionCount := 0
	longTermCount := 0
	for _, fact := range s.facts {
		if fact.UserID != userID || fact.Status != preferencemodel.StatusActive {
			continue
		}
		switch fact.Scope {
		case preferencemodel.ScopeSession:
			if fact.ConversationID != conversationID ||
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
		items = append(items, fact)
	}
	return items, nil
}

func (s *memoryPreferenceStore) GetOwned(
	_ context.Context,
	userID string,
	preferenceID string,
) (preferencemodel.Fact, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	fact, ok := s.facts[preferenceID]
	if !ok || fact.UserID != userID {
		return preferencemodel.Fact{}, false, nil
	}
	return fact, true, nil
}

func (s *memoryPreferenceStore) UpdateStatus(
	_ context.Context,
	userID string,
	preferenceID string,
	expectedVersion int64,
	update preferenceports.StatusUpdate,
) (preferencemodel.Fact, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	fact, ok := s.facts[preferenceID]
	if !ok || fact.UserID != userID || fact.Version != expectedVersion {
		return preferencemodel.Fact{}, false, nil
	}
	fact.Status = update.Status
	fact.RevokedAt = update.RevokedAt
	fact.RevocationDeadline = update.RevocationDeadline
	fact.UpdatedAt = update.UpdatedAt
	fact.Version++
	s.facts[preferenceID] = fact
	return fact, true, nil
}

type ownedConversationReader struct {
	userID         string
	conversationID string
}

func (r ownedConversationReader) OwnedConversationExists(
	_ context.Context,
	userID string,
	conversationID string,
) (bool, error) {
	return userID == r.userID && conversationID == r.conversationID, nil
}

func TestPreferenceFactSessionLifecycleAndOwnerIsolation(t *testing.T) {
	store := newMemoryPreferenceStore()
	now := time.Date(2026, 7, 20, 12, 0, 0, 0, time.UTC)
	commands := NewCommandFacade(
		store,
		ownedConversationReader{
			userID:         "persona-owner",
			conversationID: "acv-owned",
		},
	)
	commands.now = func() time.Time { return now }
	queries := NewQueryFacade(store)

	if _, err := commands.SetPreference(t.Context(), SetPreferenceCommand{
		UserID:         "another-persona",
		Scope:          "session",
		ConversationID: "acv-owned",
		Kind:           "reply_length",
		Value:          "concise",
		SourceType:     "explicit_rewrite",
	}); err == nil {
		t.Fatal("non-owner session preference set must fail")
	} else {
		var appErr *rterr.AppError
		if !errors.As(err, &appErr) ||
			!strings.Contains(appErr.Code.String(), "preference_not_found") {
			t.Fatalf("non-owner set error = %v", err)
		}
	}

	fact, err := commands.SetPreference(t.Context(), SetPreferenceCommand{
		UserID:         "persona-owner",
		Scope:          "session",
		ConversationID: "acv-owned",
		Kind:           "reply_length",
		Value:          "concise",
		SourceType:     "explicit_rewrite",
	})
	if err != nil {
		t.Fatalf("SetPreference() error = %v", err)
	}
	if fact.Status != preferencemodel.StatusActive || fact.Version != 1 {
		t.Fatalf("fact = %#v", fact)
	}

	view, err := queries.ListPreferences(t.Context(), ListPreferencesQuery{
		UserID:         "persona-owner",
		Scope:          "session",
		ConversationID: "acv-owned",
	})
	if err != nil || len(view.Items) != 1 {
		t.Fatalf("ListPreferences() view=%#v err=%v", view, err)
	}

	revoked, err := commands.RevokePreference(
		t.Context(),
		"persona-owner",
		fact.PreferenceID,
	)
	if err != nil {
		t.Fatalf("RevokePreference() error = %v", err)
	}
	if revoked.Status != preferencemodel.StatusRevoked ||
		revoked.RevocationDeadline == nil {
		t.Fatalf("revoked = %#v", revoked)
	}

	if _, err := commands.RestorePreference(
		t.Context(),
		"another-persona",
		fact.PreferenceID,
	); err == nil {
		t.Fatal("non-owner restore must fail")
	} else {
		var appErr *rterr.AppError
		if !errors.As(err, &appErr) ||
			!strings.Contains(appErr.Code.String(), "preference_not_found") {
			t.Fatalf("non-owner error = %v", err)
		}
	}

	now = now.Add(time.Minute)
	restored, err := commands.RestorePreference(
		t.Context(),
		"persona-owner",
		fact.PreferenceID,
	)
	if err != nil {
		t.Fatalf("RestorePreference() error = %v", err)
	}
	if restored.Status != preferencemodel.StatusActive ||
		restored.RevokedAt != nil ||
		restored.RevocationDeadline != nil {
		t.Fatalf("restored = %#v", restored)
	}
}

func TestPreferenceFactRestoreWindowExpiresFailClosed(t *testing.T) {
	store := newMemoryPreferenceStore()
	now := time.Date(2026, 7, 20, 12, 0, 0, 0, time.UTC)
	commands := NewCommandFacade(store, ownedConversationReader{})
	commands.now = func() time.Time { return now }

	fact, err := commands.SetPreference(t.Context(), SetPreferenceCommand{
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
		fact.PreferenceID,
	); err != nil {
		t.Fatalf("RevokePreference() error = %v", err)
	}
	now = now.Add(defaultRestoreWindow)
	if _, err := commands.RestorePreference(
		t.Context(),
		"persona-owner",
		fact.PreferenceID,
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
	store := newMemoryPreferenceStore()
	commands := NewCommandFacade(
		store,
		ownedConversationReader{
			userID:         "persona-owner",
			conversationID: "acv-owned",
		},
	)
	for _, command := range []SetPreferenceCommand{
		{
			UserID:         "persona-owner",
			Scope:          "session",
			ConversationID: "acv-owned",
			Kind:           "reply_length",
			Value:          "concise",
			SourceType:     "explicit_rewrite",
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
		"acv-owned",
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
