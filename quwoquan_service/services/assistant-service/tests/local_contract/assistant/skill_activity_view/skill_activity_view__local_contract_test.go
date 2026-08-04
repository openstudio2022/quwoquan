// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-003
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_activity_view/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_activity_view/domain/model"
)

type activitySourceStub struct {
	items []model.Item
	err   error
}

func (source activitySourceStub) ListSkillActivities(
	context.Context,
	string,
	string,
	int,
) ([]model.Item, error) {
	return append([]model.Item(nil), source.items...), source.err
}

type visibilityStoreStub struct {
	hiddenBefore *time.Time
}

func (store *visibilityStoreStub) HiddenBefore(
	context.Context,
	string,
	string,
) (*time.Time, error) {
	return store.hiddenBefore, nil
}

func (store *visibilityStoreStub) HideBefore(
	_ context.Context,
	_ string,
	_ string,
	hiddenBefore time.Time,
) error {
	value := hiddenBefore.UTC()
	if store.hiddenBefore == nil || value.After(*store.hiddenBefore) {
		store.hiddenBefore = &value
	}
	return nil
}

func TestSkillActivityFederationIsOwnerScopedRedactedAndCursorBounded(t *testing.T) {
	t.Parallel()
	base := time.Date(2026, 8, 4, 8, 0, 0, 0, time.UTC)
	hiddenBefore := base.Add(time.Minute)
	visibility := &visibilityStoreStub{hiddenBefore: &hiddenBefore}
	items := []model.Item{
		activityItem("run-new", model.KindRun, base.Add(3*time.Minute), 3),
		activityItem("consent-mid", model.KindConsent, base.Add(2*time.Minute), 0),
		activityItem("run-hidden", model.KindRun, base, 1),
	}
	facade := application.NewQueryFacade(
		visibility,
		activitySourceStub{items: items},
		activitySourceStub{items: []model.Item{items[0]}},
	)

	first, err := facade.List(
		context.Background(), "account-a", "travel_companion", "", 1,
	)
	if err != nil {
		t.Fatalf("List() error=%v", err)
	}
	if len(first.Items) != 1 || first.Items[0].ActivityID != "run-new" || first.NextCursor == "" {
		t.Fatalf("first page=%+v", first)
	}
	first.Items[0].RunID = "run-owner-only"
	first.Items[0].DataControlRequestID = "data-control-recoverable"
	encoded, err := json.Marshal(first)
	if err != nil {
		t.Fatalf("Marshal() error=%v", err)
	}
	if strings.Contains(string(encoded), "account-a") ||
		strings.Contains(string(encoded), "run-owner-only") {
		t.Fatalf("public activity wire leaked owner-only identity: %s", encoded)
	}
	if !strings.Contains(string(encoded), "data-control-recoverable") {
		t.Fatalf("public activity wire omitted typed data-control recovery target: %s", encoded)
	}
	if len(first.ExternalSources) != 2 ||
		first.ExternalSources[0].OperationRef != "integration.connector_connection.ListConnectorConnections" ||
		first.ExternalSources[1].OperationRef != "integration.connector_invocation.ListConnectorInvocations" {
		t.Fatalf("external source refs=%+v", first.ExternalSources)
	}

	second, err := facade.List(
		context.Background(), "account-a", "travel_companion", first.NextCursor, 2,
	)
	if err != nil {
		t.Fatalf("List(next) error=%v", err)
	}
	if len(second.Items) != 1 || second.Items[0].ActivityID != "consent-mid" {
		t.Fatalf("second page=%+v", second)
	}
}

func TestSkillActivityFederationFailsClosedOnMalformedOrUnavailableSource(t *testing.T) {
	t.Parallel()
	facade := application.NewQueryFacade(
		&visibilityStoreStub{},
		activitySourceStub{items: []model.Item{{ActivityID: "malformed"}}},
	)
	if _, err := facade.List(
		context.Background(), "account-a", "travel_companion", "", 20,
	); !errors.Is(err, model.ErrUnavailable) {
		t.Fatalf("malformed source error=%v, want unavailable", err)
	}
	facade = application.NewQueryFacade(
		&visibilityStoreStub{},
		activitySourceStub{err: errors.New("owner store down")},
	)
	if _, err := facade.List(
		context.Background(), "account-a", "travel_companion", "", 20,
	); !errors.Is(err, model.ErrUnavailable) {
		t.Fatalf("unavailable source error=%v, want unavailable", err)
	}
}

func activityItem(
	id string,
	kind model.ActivityKind,
	occurredAt time.Time,
	revision int64,
) model.Item {
	status := "completed"
	if kind == model.KindConsent {
		status = "granted"
	}
	semantics, err := model.ResolveSemantics(kind, status)
	if err != nil {
		panic(err)
	}
	return model.Item{
		ActivityID:      id,
		AccountID:       "account-a",
		SkillID:         "travel_companion",
		ActivityKind:    kind,
		Status:          status,
		DisplayKey:      semantics.DisplayKey,
		SourceObjectRef: "assistant.Object:" + id,
		SourceRevision:  revision,
		RecoveryAction:  semantics.RecoveryAction,
		OccurredAt:      occurredAt,
	}
}
