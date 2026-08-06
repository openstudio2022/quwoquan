// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-001
package local_contract

import (
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestCircleGroupChatProjectorsDeclareTheirDurableSources(t *testing.T) {
	_, sourcePath, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source path")
	}
	serviceRoot := filepath.Clean(filepath.Join(filepath.Dir(sourcePath), "../../../.."))
	assertChatLifecycleConsumers(
		t,
		serviceRoot,
		"conversation",
		[]string{
			"circle.circle_group.CircleGroupCreated",
			"circle.circle_group.CircleGroupArchived",
			"user.user_account.UserAvatarUpdated",
		},
		[]chatLifecycleConsumer{
			{
				Name: "ProjectCircleGroupConversation", Kind: "event_handler",
				Facet: "CircleGroupConversationProjectionHandler", Method: "apply", Idempotency: "event_id",
			},
			{
				Name: "ConsumeUserAvatarUpdated", Kind: "event_handler",
				Facet: "UserAvatarUpdateConsumer", Method: "handleMessage", Idempotency: "identity_payload_digest",
			},
		},
	)
	assertChatLifecycleConsumers(
		t,
		serviceRoot,
		"conversation_membership",
		[]string{
			"circle.circle_group_membership.CircleGroupMembershipActivated",
			"circle.circle_group_membership.CircleGroupMembershipLeft",
			"circle.circle_group_membership.CircleGroupMembershipRemoved",
			"circle.circle_group_membership.CircleGroupMembershipRoleChanged",
		},
		[]chatLifecycleConsumer{{
			Name: "ProjectCircleGroupMembership", Kind: "event_handler",
			Facet: "CircleGroupMembershipProjectionHandler", Method: "apply", Idempotency: "event_id",
		}},
	)
}

type chatLifecycleConsumer struct {
	Name        string `yaml:"name"`
	Kind        string `yaml:"kind"`
	Facet       string `yaml:"facet"`
	Method      string `yaml:"method"`
	Idempotency string `yaml:"idempotency"`
}

func assertChatLifecycleConsumers(
	t *testing.T,
	serviceRoot string,
	object string,
	wantSources []string,
	wantConsumers []chatLifecycleConsumer,
) {
	t.Helper()
	objectData, err := os.ReadFile(filepath.Join(serviceRoot, "contracts", "chat", object, "object.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Lifecycle struct {
			SourceEvents   []string                `yaml:"source_events"`
			EventConsumers []chatLifecycleConsumer `yaml:"event_consumers"`
		} `yaml:"lifecycle"`
	}
	if err := yaml.Unmarshal(objectData, &document); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(document.Lifecycle.SourceEvents, wantSources) ||
		!reflect.DeepEqual(document.Lifecycle.EventConsumers, wantConsumers) {
		t.Fatalf(
			"chat.%s lifecycle sources=%#v consumers=%#v, want sources=%#v consumers=%#v",
			object,
			document.Lifecycle.SourceEvents,
			document.Lifecycle.EventConsumers,
			wantSources,
			wantConsumers,
		)
	}
	operationsData, err := os.ReadFile(filepath.Join(serviceRoot, "contracts", "chat", object, "operations.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var operations map[string]any
	if err := yaml.Unmarshal(operationsData, &operations); err != nil {
		t.Fatal(err)
	}
	if _, legacy := operations["runtime_entrypoints"]; legacy {
		t.Fatalf("chat.%s HTTP object retains legacy operations.runtime_entrypoints", object)
	}
}
