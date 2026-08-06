// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-002
package local_contract

import (
	"testing"
	"time"

	callsession "quwoquan_service/services/rtc-service/internal/rtc/call_session/domain"
	rtcconfig "quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/runtimeconfig"
)

func TestRingTimeoutConfigurationResolvesOneTypedPolicy(t *testing.T) {
	t.Parallel()

	configuration, err := (rtcconfig.RingTimeoutSettings{
		SweepIntervalMilliseconds:   250,
		OneToOneTimeoutMilliseconds: 17000,
		GroupTimeoutMilliseconds:    41000,
	}).Resolve()
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if configuration.SweepInterval != 250*time.Millisecond {
		t.Fatalf("sweep interval = %s, want 250ms", configuration.SweepInterval)
	}
	if configuration.DomainPolicy.OneToOne() != 17*time.Second {
		t.Fatalf(
			"one-to-one timeout = %s, want 17s",
			configuration.DomainPolicy.OneToOne(),
		)
	}
	if configuration.DomainPolicy.Group() != 41*time.Second {
		t.Fatalf(
			"group timeout = %s, want 41s",
			configuration.DomainPolicy.Group(),
		)
	}
}

func TestRingTimeoutConfigurationFailsClosed(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name     string
		settings rtcconfig.RingTimeoutSettings
	}{
		{
			name: "zero sweep interval",
			settings: rtcconfig.RingTimeoutSettings{
				OneToOneTimeoutMilliseconds: 17000,
				GroupTimeoutMilliseconds:    41000,
			},
		},
		{
			name: "negative one-to-one timeout",
			settings: rtcconfig.RingTimeoutSettings{
				SweepIntervalMilliseconds:   250,
				OneToOneTimeoutMilliseconds: -1,
				GroupTimeoutMilliseconds:    41000,
			},
		},
		{
			name: "zero group timeout",
			settings: rtcconfig.RingTimeoutSettings{
				SweepIntervalMilliseconds:   250,
				OneToOneTimeoutMilliseconds: 17000,
			},
		},
		{
			name: "one-to-one exceeds group timeout",
			settings: rtcconfig.RingTimeoutSettings{
				SweepIntervalMilliseconds:   250,
				OneToOneTimeoutMilliseconds: 41001,
				GroupTimeoutMilliseconds:    41000,
			},
		},
	}

	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			if _, err := test.settings.Resolve(); err == nil {
				t.Fatal("Resolve() accepted invalid ring-timeout settings")
			}
		})
	}
}

func TestCallSessionServiceRejectsUnresolvedRingTimeoutPolicy(t *testing.T) {
	t.Parallel()

	if _, err := callsession.NewCallSessionService(callsession.RingTimeoutPolicy{}); err == nil {
		t.Fatal("NewCallSessionService() accepted the zero-value timeout policy")
	}
}
