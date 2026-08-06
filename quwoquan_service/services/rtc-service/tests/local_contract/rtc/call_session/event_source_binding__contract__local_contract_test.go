// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
package local_contract

import (
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestCallSessionAccountSecurityLifecycleConsumerIsSingleTrack(t *testing.T) {
	_, source, _, _ := runtime.Caller(0)
	root := filepath.Clean(filepath.Join(filepath.Dir(source), "../../../.."))
	raw, err := os.ReadFile(filepath.Join(root, "contracts/rtc/call_session/object.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Lifecycle struct {
			SourceEvents   []string `yaml:"source_events"`
			EventConsumers []struct {
				Name        string `yaml:"name"`
				Kind        string `yaml:"kind"`
				Facet       string `yaml:"facet"`
				Method      string `yaml:"method"`
				Idempotency string `yaml:"idempotency"`
			} `yaml:"event_consumers"`
		} `yaml:"lifecycle"`
	}
	if err := yaml.Unmarshal(raw, &document); err != nil {
		t.Fatal(err)
	}
	want := []string{
		"user.user_account.UserSuspended",
		"user.user_account.UserRestored",
		"user.user_account.UserAccountClosed",
		"rtc.call_session.CallInitiated",
		"rtc.call_session.CallRinging",
		"rtc.call_session.CallAnswered",
		"rtc.call_session.CallConnected",
		"rtc.call_session.CallEnded",
		"rtc.call_session.ParticipantJoined",
		"rtc.call_session.ParticipantLeft",
		"rtc.call_session.ScreenShareStarted",
		"rtc.call_session.ScreenShareStopped",
	}
	if len(document.Lifecycle.EventConsumers) != 2 ||
		document.Lifecycle.EventConsumers[0].Name != "ApplyAccountSecurityTerminalEvent" ||
		document.Lifecycle.EventConsumers[0].Kind != "event_handler" ||
		document.Lifecycle.EventConsumers[0].Facet != "CallOrchestrator" ||
		document.Lifecycle.EventConsumers[0].Method != "applyAccountSecurityTerminalEvent" ||
		document.Lifecycle.EventConsumers[0].Idempotency != "event_id" ||
		document.Lifecycle.EventConsumers[1].Name != "DeliverRealtimeCallSignals" ||
		document.Lifecycle.EventConsumers[1].Kind != "event_handler" ||
		document.Lifecycle.EventConsumers[1].Facet != "CallSignalDeliveryCoordinator" ||
		document.Lifecycle.EventConsumers[1].Method != "deliver" ||
		document.Lifecycle.EventConsumers[1].Idempotency != "event_id" ||
		!reflect.DeepEqual(document.Lifecycle.SourceEvents, want) {
		t.Fatalf("call session lifecycle event binding drifted: %+v", document.Lifecycle)
	}
}
