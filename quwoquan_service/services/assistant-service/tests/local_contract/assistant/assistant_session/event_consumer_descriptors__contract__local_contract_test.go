// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-001
package local_contract

import (
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestAssistantEventConsumerDescriptorsMatchProductionHandlers(t *testing.T) {
	root := assistantEventServiceRoot(t)
	assertAssistantLifecycleConsumers(
		t,
		root,
		"assistant_learning_fact",
		[]string{"assistant.assistant_run.AssistantRunCompleted"},
		[]assistantLifecycleConsumer{{
			Name: "AppendTerminalAssistantLearningFact", Kind: "subscription",
			Facet: "AssistantLearningFactAppender", Method: "appendTerminalRun", Idempotency: "event_id",
		}},
	)
	assertAssistantLifecycleConsumers(
		t,
		root,
		"assistant_session",
		[]string{
			"chat.message.AssistantMentioned",
			"assistant.assistant_run.AssistantRunCompleted",
		},
		[]assistantLifecycleConsumer{
			{
				Name: "HandleAssistantMentioned", Kind: "event_handler",
				Facet: "AssistantMentionedConsumer", Method: "processOnce", Idempotency: "event_id",
			},
			{
				Name: "CompactAssistantSessionOnRunCompleted", Kind: "event_handler",
				Facet: "AssistantRunTerminalCoordinator", Method: "compactSession", Idempotency: "event_id",
			},
		},
	)
}

type assistantLifecycleConsumer struct {
	Name        string `yaml:"name"`
	Kind        string `yaml:"kind"`
	Facet       string `yaml:"facet"`
	Method      string `yaml:"method"`
	Idempotency string `yaml:"idempotency"`
}

func assistantEventServiceRoot(t *testing.T) string {
	t.Helper()
	_, path, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(path), "../../../.."))
}

func assertAssistantLifecycleConsumers(
	t *testing.T,
	root string,
	object string,
	wantSources []string,
	wantConsumers []assistantLifecycleConsumer,
) {
	t.Helper()
	objectData, err := os.ReadFile(filepath.Join(root, "contracts", "assistant", object, "object.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Lifecycle struct {
			SourceEvents   []string                     `yaml:"source_events"`
			EventConsumers []assistantLifecycleConsumer `yaml:"event_consumers"`
		} `yaml:"lifecycle"`
	}
	if err := yaml.Unmarshal(objectData, &document); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(document.Lifecycle.SourceEvents, wantSources) ||
		!reflect.DeepEqual(document.Lifecycle.EventConsumers, wantConsumers) {
		t.Fatalf(
			"%s lifecycle sources=%#v consumers=%#v, want sources=%#v consumers=%#v",
			object,
			document.Lifecycle.SourceEvents,
			document.Lifecycle.EventConsumers,
			wantSources,
			wantConsumers,
		)
	}
	operationsData, err := os.ReadFile(filepath.Join(root, "contracts", "assistant", object, "operations.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var operations map[string]any
	if err := yaml.Unmarshal(operationsData, &operations); err != nil {
		t.Fatal(err)
	}
	if _, legacy := operations["runtime_entrypoints"]; legacy {
		t.Fatalf("%s HTTP object retains legacy operations.runtime_entrypoints", object)
	}
}
