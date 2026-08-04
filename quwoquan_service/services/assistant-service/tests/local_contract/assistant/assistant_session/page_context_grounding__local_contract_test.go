// spec_ref: specs/feature-tree/runtime/runtime-assistant/context-grounded-answering/spec.md#gwt-001
package local_contract

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
	"time"

	runapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	rundomain "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	pageapplication "quwoquan_service/services/assistant-service/internal/assistant/page_context/application"
	pagemodel "quwoquan_service/services/assistant-service/internal/assistant/page_context/domain/model"
	assistantruntest "quwoquan_service/services/assistant-service/tests/support/assistantrun"
)

type pageContextStore struct{ current *pagemodel.PageContext }

func (store *pageContextStore) Put(_ context.Context, value pagemodel.PageContext) error {
	store.current = &value
	return nil
}

func (store *pageContextStore) Get(context.Context, string) (*pagemodel.PageContext, error) {
	return store.current, nil
}

func TestCanonicalPageContextEntersTheNextTurnPrompt(t *testing.T) {
	now := time.Date(2026, 8, 2, 12, 0, 0, 0, time.UTC)
	pages := pageapplication.NewFacade(
		&pageContextStore{},
		func() time.Time { return now },
	)
	if _, err := pages.Report(t.Context(), "account-1", "persona-1", pagemodel.Snapshot{
		CapturedAt: now,
		PageType:   "article",
		PageObjects: []pagemodel.ObjectRef{{
			ObjectTypeRef: "content.Post",
			ObjectID:      "post-1",
		}},
		UserActions: []pagemodel.Action{{
			ActionType:    "open_assistant_entry",
			ObjectTypeRef: "content.Post",
			ObjectID:      "post-1",
		}},
		ConsentGranted: true,
	}); err != nil {
		t.Fatal(err)
	}

	runtime := assistantruntest.NewMemoryRuntime()
	commands := runruntime.NewCommandService(
		runtime,
		runruntime.SessionResolverFunc(func(context.Context, string, string) (runruntime.SessionContinuity, error) {
			return runruntime.SessionContinuity{}, nil
		}),
		testSkillPackageIdentityResolver(),
		runruntime.AllowAllStartAccessPolicy{},
		func() time.Time { return now },
		nil,
		runruntime.WithPolicyResolver(testRunPolicyResolver()),
	)
	resolver := runapplication.NewContextResolver(
		runapplication.CurrentPageContextReaderFunc(func(
			ctx context.Context,
			accountID string,
		) (map[string]any, bool, error) {
			current, readErr := pages.Current(ctx, accountID)
			if readErr != nil || current == nil {
				return nil, false, readErr
			}
			return map[string]any{
				"capturedAt": current.CapturedAt,
				"pageType":   current.Snapshot.PageType,
				"pageObjects": []any{map[string]any{
					"objectTypeRef": current.Snapshot.PageObjects[0].ObjectTypeRef,
					"objectId":      current.Snapshot.PageObjects[0].ObjectID,
				}},
				"userActions": []any{map[string]any{
					"action":        current.Snapshot.UserActions[0].ActionType,
					"objectTypeRef": current.Snapshot.UserActions[0].ObjectTypeRef,
					"objectId":      current.Snapshot.UserActions[0].ObjectID,
				}},
				"consentMatrix": map[string]any{"canReadCurrentPage": true},
			}, true, nil
		}),
		nil,
	)
	run, err := runapplication.NewUseCases(
		commands,
		runapplication.WithContextResolver(resolver),
	).Start(
		t.Context(),
		"account-1",
		"page-context-session",
		"trace-page-context",
		runapplication.StartInput{
			ClientRequestID: "page-context-run",
			Intent: rundomain.Intent{
				Kind:   "answer",
				Answer: &rundomain.AnswerIntent{Text: "结合当前页面回答"},
			},
			TrustedPersonaID: "persona-1",
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	encoded, err := json.Marshal(run.ContextSnapshot)
	if err != nil {
		t.Fatal(err)
	}
	var snapshot assistant.AssistantContextSnapshot
	if err := json.Unmarshal(encoded, &snapshot); err != nil {
		t.Fatal(err)
	}
	if snapshot.PageType != "article" || len(snapshot.PageObjects) != 1 {
		t.Fatalf("run page context=%#v", snapshot)
	}
	prompt := orchestration.FormatPageContextForPrompt(&snapshot)
	if !strings.Contains(prompt, "content.Post:post-1") ||
		!strings.Contains(prompt, "open_assistant_entry") {
		t.Fatalf("page context prompt=%q", prompt)
	}
}

func TestMissingPageContextCannotEnterPrompt(t *testing.T) {
	runtime := assistantruntest.NewMemoryRuntime()
	commands := runruntime.NewCommandService(
		runtime,
		runruntime.SessionResolverFunc(func(context.Context, string, string) (runruntime.SessionContinuity, error) {
			return runruntime.SessionContinuity{}, nil
		}),
		testSkillPackageIdentityResolver(),
		runruntime.AllowAllStartAccessPolicy{},
		nil,
		nil,
		runruntime.WithPolicyResolver(testRunPolicyResolver()),
	)
	requested := map[string]any{
		"capturedAt":    "2026-08-02T00:00:00Z",
		"pageType":      "trip_timeline",
		"pageObjects":   []any{map[string]any{"objectTypeRef": "travel.TripPlan", "objectId": "trip-secret"}},
		"userActions":   []any{map[string]any{"action": "open_private_trip"}},
		"consentMatrix": map[string]any{"canReadCurrentPage": true},
		"tripId":        "trip-secret",
		"clientHint":    "preserved",
	}
	run, err := runapplication.NewUseCases(
		commands,
		runapplication.WithContextResolver(runapplication.NewContextResolver(nil, nil)),
	).Start(t.Context(), "account-1", "missing-page-context-session", "trace-missing", runapplication.StartInput{
		ClientRequestID: "missing-page-context-run",
		ContextSnapshot: requested,
		Intent: rundomain.Intent{
			Kind:   "answer",
			Answer: &rundomain.AnswerIntent{Text: "回答问题"},
		},
		TrustedPersonaID: "persona-1",
	})
	if err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{
		"capturedAt", "pageType", "pageObjects", "userActions", "consentMatrix",
	} {
		if _, ok := run.ContextSnapshot[key]; ok {
			t.Fatalf("untrusted %s entered run: %#v", key, run.ContextSnapshot)
		}
	}
	if run.ContextSnapshot["clientHint"] != "preserved" || run.ContextSnapshot["tripId"] != "trip-secret" {
		t.Fatalf("non-page client context was unexpectedly changed: %#v", run.ContextSnapshot)
	}
}

func TestCanonicalPageContextReplacesSpoofedClientValues(t *testing.T) {
	resolver := runapplication.NewContextResolver(
		runapplication.CurrentPageContextReaderFunc(func(
			context.Context,
			string,
		) (map[string]any, bool, error) {
			return map[string]any{
				"pageType": "article",
				"pageObjects": []any{map[string]any{
					"objectTypeRef": "content.Post", "objectId": "post-canonical",
				}},
			}, true, nil
		}),
		nil,
	)
	resolved, err := resolver.Resolve(t.Context(), "account-1", "persona-1", map[string]any{
		"pageType": "trip_timeline",
		"pageObjects": []any{map[string]any{
			"objectTypeRef": "travel.TripPlan", "objectId": "trip-secret",
		}},
		"userActions":   []any{map[string]any{"action": "spoofed"}},
		"consentMatrix": map[string]any{"canReadCurrentPage": true},
	})
	if err != nil {
		t.Fatal(err)
	}
	if resolved["pageType"] != "article" {
		t.Fatalf("page type was not replaced: %#v", resolved)
	}
	encoded, _ := json.Marshal(resolved["pageObjects"])
	if strings.Contains(string(encoded), "trip-secret") || !strings.Contains(string(encoded), "post-canonical") {
		t.Fatalf("page objects were not replaced: %s", encoded)
	}
	if _, ok := resolved["userActions"]; ok {
		t.Fatalf("missing canonical user actions preserved spoofed values: %#v", resolved)
	}
	if _, ok := resolved["consentMatrix"]; ok {
		t.Fatalf("missing canonical consent matrix preserved spoofed values: %#v", resolved)
	}
}
