// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
package local_contract

import (
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestChatInboxAndRtcMessageDeclareOnlyProductionEventSources(t *testing.T) {
	root := chatServiceRoot(t)
	assertChatLifecycleConsumers(
		t,
		root,
		"chat_inbox_view",
		[]string{
			"chat.message.MessageSent",
			"chat.message.MessageRecalled",
			"chat.conversation.ConversationCreated",
			"chat.conversation.ConversationRosterUpdated",
			"chat.conversation.ConversationAvatarUpdated",
			"chat.conversation.ConversationDissolved",
			"chat.conversation_membership.ConversationMemberAdded",
			"chat.conversation_membership.ConversationMemberRemoved",
			"chat.conversation_membership.ConversationMemberLeft",
			"chat.conversation_membership.ConversationMemberRoleChanged",
			"chat.conversation_user_state.ConversationReadWatermarkAdvanced",
			"chat.conversation_user_state.ConversationUserSettingsChanged",
		},
		[]chatLifecycleConsumer{{
			Name: "ProjectChatInbox", Kind: "projector", Facet: "ChatInboxViewProjector",
			Method: "apply", Idempotency: "aggregate_version",
		}},
		"per_source_outbox_sequence",
		"enumerate_conversation_user_state_identities",
		"hide_inactive_or_inaccessible_conversation_keep_checkpoint",
	)
	assertChatLifecycleConsumers(
		t,
		root,
		"message",
		[]string{"rtc.call_session.CallEnded"},
		[]chatLifecycleConsumer{{
			Name: "AppendRtcCallLog", Kind: "event_handler", Facet: "RtcCallLogHandler",
			Method: "appendRtcCallLog", Idempotency: "event_id",
		}},
		"",
		"",
		"",
	)
}

type chatLifecycleConsumer struct {
	Name        string `yaml:"name"`
	Kind        string `yaml:"kind"`
	Facet       string `yaml:"facet"`
	Method      string `yaml:"method"`
	Idempotency string `yaml:"idempotency"`
}

func chatServiceRoot(t *testing.T) string {
	t.Helper()
	_, path, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(path), "../../../.."))
}

func assertChatLifecycleConsumers(
	t *testing.T,
	root string,
	object string,
	wantSources []string,
	wantConsumers []chatLifecycleConsumer,
	wantCheckpoint string,
	wantRebuild string,
	wantTombstone string,
) {
	t.Helper()
	objectData, err := os.ReadFile(filepath.Join(root, "contracts", "chat", object, "object.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Lifecycle struct {
			SourceEvents   []string                `yaml:"source_events"`
			EventConsumers []chatLifecycleConsumer `yaml:"event_consumers"`
			Checkpoint     string                  `yaml:"checkpoint"`
			Rebuild        string                  `yaml:"rebuild"`
			Tombstone      string                  `yaml:"tombstone"`
		} `yaml:"lifecycle"`
	}
	if err := yaml.Unmarshal(objectData, &document); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(document.Lifecycle.SourceEvents, wantSources) ||
		!reflect.DeepEqual(document.Lifecycle.EventConsumers, wantConsumers) ||
		document.Lifecycle.Checkpoint != wantCheckpoint ||
		document.Lifecycle.Rebuild != wantRebuild ||
		document.Lifecycle.Tombstone != wantTombstone {
		t.Fatalf(
			"chat.%s lifecycle=%+v, want sources=%#v consumers=%#v checkpoint=%q rebuild=%q tombstone=%q",
			object,
			document.Lifecycle,
			wantSources,
			wantConsumers,
			wantCheckpoint,
			wantRebuild,
			wantTombstone,
		)
	}
	operationsData, err := os.ReadFile(filepath.Join(root, "contracts", "chat", object, "operations.yaml"))
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
