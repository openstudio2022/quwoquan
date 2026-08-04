// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-003
package local_contract

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"testing"
	"time"

	"gopkg.in/yaml.v3"

	runruntime "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	activitymodel "quwoquan_service/services/assistant-service/internal/assistant/skill_activity_view/domain/model"
	activitysource "quwoquan_service/services/assistant-service/internal/assistant/skill_activity_view/infrastructure/source"
	consentmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/model"
	datacontrolmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/model"
	subscriptionmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
)

func TestSkillActivityAndDataControlWireClosuresMatchCanonicalEnums(t *testing.T) {
	t.Parallel()
	var document struct {
		Enums []struct {
			Name   string `yaml:"name"`
			Values []struct {
				Wire string `yaml:"wire"`
			} `yaml:"values"`
		} `yaml:"enums"`
	}
	payload, err := os.ReadFile(filepath.Join(
		assistantServiceContractRoot(t), "contracts", "_shared", "enums.yaml",
	))
	if err != nil {
		t.Fatalf("read assistant enums: %v", err)
	}
	if err := yaml.Unmarshal(payload, &document); err != nil {
		t.Fatalf("parse assistant enums: %v", err)
	}
	wiresByName := map[string][]string{}
	for _, enum := range document.Enums {
		for _, value := range enum.Values {
			wiresByName[enum.Name] = append(wiresByName[enum.Name], value.Wire)
		}
	}
	assertSameWireClosure(t, wiresByName["SkillDataControlAction"], []string{
		datacontrolmodel.ActionHideActivityHistory,
		datacontrolmodel.ActionRevokeConsent,
		datacontrolmodel.ActionArchiveSubscriptions,
	})
	assertSameWireClosure(t, wiresByName["SkillActivityKind"], []string{
		string(activitymodel.KindRun),
		string(activitymodel.KindConsent),
		string(activitymodel.KindSubscription),
		string(activitymodel.KindDataControl),
	})
	assertSameWireClosure(t, wiresByName["SkillActivityRecoveryAction"], []string{
		string(activitymodel.RecoveryRetryRun),
		string(activitymodel.RecoveryProvideInput),
		string(activitymodel.RecoveryReviewApproval),
		string(activitymodel.RecoveryResumeRun),
		string(activitymodel.RecoveryReviewConsent),
		string(activitymodel.RecoveryManageConsent),
		string(activitymodel.RecoveryResumeSubscription),
		string(activitymodel.RecoveryManageSubscription),
		string(activitymodel.RecoveryRetryDataControl),
	})
	assertSameWireClosure(t, wiresByName["SkillActivityDisplayKey"], []string{
		string(activitymodel.DisplayRunAccepted),
		string(activitymodel.DisplayRunOrienting),
		string(activitymodel.DisplayRunPlanning),
		string(activitymodel.DisplayRunExecuting),
		string(activitymodel.DisplayRunObserving),
		string(activitymodel.DisplayRunReflecting),
		string(activitymodel.DisplayRunCheckpointing),
		string(activitymodel.DisplayRunWaitingUser),
		string(activitymodel.DisplayRunWaitingApproval),
		string(activitymodel.DisplayRunWaitingExternal),
		string(activitymodel.DisplayRunPaused),
		string(activitymodel.DisplayRunSynthesizing),
		string(activitymodel.DisplayRunVerifying),
		string(activitymodel.DisplayRunCompleted),
		string(activitymodel.DisplayRunFailed),
		string(activitymodel.DisplayRunCancelled),
		string(activitymodel.DisplayConsentGranted),
		string(activitymodel.DisplayConsentRevoked),
		string(activitymodel.DisplaySubscriptionActive),
		string(activitymodel.DisplaySubscriptionPaused),
		string(activitymodel.DisplaySubscriptionArchived),
		string(activitymodel.DisplayDataControlPendingConfirmation),
		string(activitymodel.DisplayDataControlExecuting),
		string(activitymodel.DisplayDataControlCompleted),
		string(activitymodel.DisplayDataControlCancelled),
		string(activitymodel.DisplayDataControlFailed),
	})
}

func assistantServiceContractRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", ".."))
}

func assertSameWireClosure(t *testing.T, actual, expected []string) {
	t.Helper()
	actual = append([]string(nil), actual...)
	expected = append([]string(nil), expected...)
	sort.Strings(actual)
	sort.Strings(expected)
	if len(actual) != len(expected) {
		t.Fatalf("wire closure count=%d, want %d: actual=%v expected=%v", len(actual), len(expected), actual, expected)
	}
	for index := range actual {
		if actual[index] != expected[index] {
			t.Fatalf("wire closure drift: actual=%v expected=%v", actual, expected)
		}
	}
}

type runActivityReaderStub struct {
	events []runruntime.SkillActivityEvent
}

func (stub runActivityReaderStub) ListSkillActivityEvents(
	context.Context,
	string,
	string,
	int,
) ([]runruntime.SkillActivityEvent, error) {
	return append([]runruntime.SkillActivityEvent(nil), stub.events...), nil
}

type consentActivityReaderStub struct{ events []consentmodel.Event }

func (stub consentActivityReaderStub) ListSkillConsentEvents(
	context.Context,
	string,
	string,
	int,
) ([]consentmodel.Event, error) {
	return append([]consentmodel.Event(nil), stub.events...), nil
}

type subscriptionActivityReaderStub struct {
	events []subscriptionmodel.ActivityEvent
}

func (stub subscriptionActivityReaderStub) ListSkillSubscriptionActivities(
	context.Context,
	string,
	string,
	int,
) ([]subscriptionmodel.ActivityEvent, error) {
	return append([]subscriptionmodel.ActivityEvent(nil), stub.events...), nil
}

type dataControlActivityReaderStub struct {
	events []datacontrolmodel.ActivityEvent
}

func (stub dataControlActivityReaderStub) ListSkillDataControlActivities(
	context.Context,
	string,
	string,
	int,
) ([]datacontrolmodel.ActivityEvent, error) {
	return append([]datacontrolmodel.ActivityEvent(nil), stub.events...), nil
}

func TestSkillActivitySemanticsCoverCanonicalOwnerStateClosure(t *testing.T) {
	t.Parallel()
	tests := []struct {
		kind     activitymodel.ActivityKind
		status   string
		display  activitymodel.DisplayKey
		recovery activitymodel.RecoveryAction
	}{
		{activitymodel.KindRun, "accepted", activitymodel.DisplayRunAccepted, ""},
		{activitymodel.KindRun, "orienting", activitymodel.DisplayRunOrienting, ""},
		{activitymodel.KindRun, "planning", activitymodel.DisplayRunPlanning, ""},
		{activitymodel.KindRun, "executing", activitymodel.DisplayRunExecuting, ""},
		{activitymodel.KindRun, "observing", activitymodel.DisplayRunObserving, ""},
		{activitymodel.KindRun, "reflecting", activitymodel.DisplayRunReflecting, ""},
		{activitymodel.KindRun, "checkpointing", activitymodel.DisplayRunCheckpointing, ""},
		{activitymodel.KindRun, "waiting_user", activitymodel.DisplayRunWaitingUser, activitymodel.RecoveryProvideInput},
		{activitymodel.KindRun, "waiting_approval", activitymodel.DisplayRunWaitingApproval, activitymodel.RecoveryReviewApproval},
		{activitymodel.KindRun, "waiting_external", activitymodel.DisplayRunWaitingExternal, ""},
		{activitymodel.KindRun, "paused", activitymodel.DisplayRunPaused, activitymodel.RecoveryResumeRun},
		{activitymodel.KindRun, "synthesizing", activitymodel.DisplayRunSynthesizing, ""},
		{activitymodel.KindRun, "verifying", activitymodel.DisplayRunVerifying, ""},
		{activitymodel.KindRun, "completed", activitymodel.DisplayRunCompleted, ""},
		{activitymodel.KindRun, "failed", activitymodel.DisplayRunFailed, activitymodel.RecoveryRetryRun},
		{activitymodel.KindRun, "cancelled", activitymodel.DisplayRunCancelled, ""},
		{activitymodel.KindConsent, "granted", activitymodel.DisplayConsentGranted, activitymodel.RecoveryManageConsent},
		{activitymodel.KindConsent, "revoked", activitymodel.DisplayConsentRevoked, activitymodel.RecoveryReviewConsent},
		{activitymodel.KindSubscription, "active", activitymodel.DisplaySubscriptionActive, activitymodel.RecoveryManageSubscription},
		{activitymodel.KindSubscription, "paused", activitymodel.DisplaySubscriptionPaused, activitymodel.RecoveryResumeSubscription},
		{activitymodel.KindSubscription, "archived", activitymodel.DisplaySubscriptionArchived, ""},
		{activitymodel.KindDataControl, "pending_confirmation", activitymodel.DisplayDataControlPendingConfirmation, ""},
		{activitymodel.KindDataControl, "executing", activitymodel.DisplayDataControlExecuting, ""},
		{activitymodel.KindDataControl, "completed", activitymodel.DisplayDataControlCompleted, ""},
		{activitymodel.KindDataControl, "cancelled", activitymodel.DisplayDataControlCancelled, ""},
		{activitymodel.KindDataControl, "failed", activitymodel.DisplayDataControlFailed, activitymodel.RecoveryRetryDataControl},
	}
	for _, test := range tests {
		test := test
		t.Run(string(test.kind)+"/"+test.status, func(t *testing.T) {
			t.Parallel()
			got, err := activitymodel.ResolveSemantics(test.kind, test.status)
			if err != nil || got.DisplayKey != test.display || got.RecoveryAction != test.recovery {
				t.Fatalf("ResolveSemantics()=%+v error=%v", got, err)
			}
		})
	}
}

func TestSkillActivitySourcesRejectUnknownOwnerState(t *testing.T) {
	t.Parallel()
	at := time.Date(2026, 8, 4, 15, 0, 0, 0, time.UTC)
	tests := []struct {
		name   string
		source interface {
			ListSkillActivities(context.Context, string, string, int) ([]activitymodel.Item, error)
		}
	}{
		{
			name: "run_unknown_state",
			source: activitysource.NewRunSource(runActivityReaderStub{events: []runruntime.SkillActivityEvent{{
				RunID: "run-1", UserID: "account-a", SkillID: "travel_companion",
				State: "invented", Revision: 1, OccurredAt: at,
			}}}),
		},
		{
			name: "consent_unknown_event",
			source: activitysource.NewConsentSource(consentActivityReaderStub{events: []consentmodel.Event{{
				EventID: "event-1", EventName: "SkillConsentInvented", AggregateID: "consent-1",
				AccountID: "account-a", SkillID: "travel_companion", OccurredAt: at,
			}}}),
		},
		{
			name: "subscription_unknown_state",
			source: activitysource.NewSubscriptionSource(subscriptionActivityReaderStub{events: []subscriptionmodel.ActivityEvent{{
				EventID: "event-1", SubscriptionID: "subscription-1", OwnerID: "account-a",
				SkillID: "travel_companion", Status: "invented", Version: 1, OccurredAt: at,
			}}}),
		},
		{
			name: "data_control_unknown_state",
			source: activitysource.NewDataControlSource(dataControlActivityReaderStub{events: []datacontrolmodel.ActivityEvent{{
				EventID: "event-1", RequestID: "request-1", AccountID: "account-a",
				SkillID: "travel_companion", Status: "invented", Revision: 1, OccurredAt: at,
			}}}),
		},
	}
	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			_, err := test.source.ListSkillActivities(
				context.Background(), "account-a", "travel_companion", 20,
			)
			if !errors.Is(err, activitymodel.ErrUnavailable) {
				t.Fatalf("ListSkillActivities() error=%v, want unavailable", err)
			}
		})
	}
}
