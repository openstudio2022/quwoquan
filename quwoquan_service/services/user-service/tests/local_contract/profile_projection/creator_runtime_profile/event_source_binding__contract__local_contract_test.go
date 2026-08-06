// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
// readiness_case: project-creator-runtime-profile-account-closure-local
package local_contract

import (
	"context"
	"os"
	"path/filepath"
	"runtime"
	"testing"
	"time"

	"gopkg.in/yaml.v3"

	creatorapp "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/application"
)

func TestCreatorRuntimeProfileUsesReleaseImportAndOnlyRealStreamConsumer(t *testing.T) {
	lifecycle, entrypoint := readCreatorRuntimeBindings(t)
	if len(lifecycle.SourceEvents) != 1 || lifecycle.SourceEvents[0] != "user.user_account.UserAccountClosed" ||
		len(lifecycle.EventConsumers) != 1 {
		t.Fatalf("creator runtime lifecycle drifted: %+v", lifecycle)
	}
	consumer := lifecycle.EventConsumers[0]
	if consumer.Name != "ProjectCreatorRuntimeProfileAccountClosure" || consumer.Kind != "projector" ||
		consumer.Facet != "AccountClosureProjector" || consumer.Method != "apply" || consumer.Idempotency != "event_id" ||
		entrypoint.Name != consumer.Name || entrypoint.Kind != consumer.Kind ||
		entrypoint.Application.Facet != consumer.Facet || entrypoint.Application.Method != consumer.Method {
		t.Fatalf("creator runtime lifecycle=%+v runtime=%+v", consumer, entrypoint)
	}

	store := &creatorAccountClosureStore{}
	projector := creatorapp.NewAccountClosureProjector(store)
	closedAt := time.Date(2026, time.August, 6, 2, 15, 0, 0, time.UTC)
	if err := projector.Apply(t.Context(), creatorapp.AccountClosedEvent{
		AccountID:  "account-closed",
		PersonaIDs: []string{"creator-persona"},
		ClosedAt:   closedAt,
	}); err != nil {
		t.Fatalf("apply production CreatorRuntimeProfile account closure: %v", err)
	}
	if store.calls != 1 || len(store.personaIDs) != 1 ||
		store.personaIDs[0] != "creator-persona" || !store.closedAt.Equal(closedAt) {
		t.Fatalf("CreatorRuntimeProfile account closure state=%+v", store)
	}
}

type creatorAccountClosureStore struct {
	calls      int
	personaIDs []string
	closedAt   time.Time
}

func (store *creatorAccountClosureStore) TombstoneForClosedSubjects(
	_ context.Context,
	personaIDs []string,
	closedAt time.Time,
) error {
	store.calls++
	store.personaIDs = append([]string(nil), personaIDs...)
	store.closedAt = closedAt
	return nil
}

type lifecycleBinding struct {
	SourceEvents   []string `yaml:"source_events"`
	EventConsumers []struct {
		Name        string `yaml:"name"`
		Kind        string `yaml:"kind"`
		Facet       string `yaml:"facet"`
		Method      string `yaml:"method"`
		Idempotency string `yaml:"idempotency"`
	} `yaml:"event_consumers"`
}

type runtimeBinding struct {
	Name        string `yaml:"name"`
	Kind        string `yaml:"kind"`
	Application struct {
		Facet  string `yaml:"facet"`
		Method string `yaml:"method"`
	} `yaml:"application"`
}

func readCreatorRuntimeBindings(t *testing.T) (lifecycleBinding, runtimeBinding) {
	t.Helper()
	_, source, _, _ := runtime.Caller(0)
	root := filepath.Clean(filepath.Join(filepath.Dir(source), "../../../.."))
	objectRaw, err := os.ReadFile(filepath.Join(root, "contracts/profile_projection/creator_runtime_profile/object.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var objectDocument struct {
		Lifecycle lifecycleBinding `yaml:"lifecycle"`
	}
	if err := yaml.Unmarshal(objectRaw, &objectDocument); err != nil {
		t.Fatal(err)
	}
	operationsRaw, err := os.ReadFile(filepath.Join(root, "contracts/profile_projection/creator_runtime_profile/operations.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var operationsDocument struct {
		RuntimeEntrypoints []runtimeBinding `yaml:"runtime_entrypoints"`
	}
	if err := yaml.Unmarshal(operationsRaw, &operationsDocument); err != nil {
		t.Fatal(err)
	}
	if len(operationsDocument.RuntimeEntrypoints) != 1 {
		t.Fatalf("runtime entrypoints=%d, want 1", len(operationsDocument.RuntimeEntrypoints))
	}
	return objectDocument.Lifecycle, operationsDocument.RuntimeEntrypoints[0]
}
