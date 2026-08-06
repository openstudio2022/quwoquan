package runtimeconfig

import (
	"fmt"
	"math"
	"time"

	callsession "quwoquan_service/services/rtc-service/internal/rtc/call_session/domain"
)

// RingTimeoutSettings is the typed YAML shape beneath
// call_session.ring_timeout in the generated service runtime configuration.
type RingTimeoutSettings struct {
	SweepIntervalMilliseconds   int `yaml:"sweep_interval_ms"`
	OneToOneTimeoutMilliseconds int `yaml:"one_to_one_timeout_ms"`
	GroupTimeoutMilliseconds    int `yaml:"group_timeout_ms"`
}

type RingTimeoutConfiguration struct {
	SweepInterval time.Duration
	DomainPolicy  callsession.RingTimeoutPolicy
}

func (s RingTimeoutSettings) Resolve() (RingTimeoutConfiguration, error) {
	sweepInterval, err := positiveMilliseconds(
		"ring-timeout sweep interval",
		s.SweepIntervalMilliseconds,
	)
	if err != nil {
		return RingTimeoutConfiguration{}, err
	}
	oneToOne, err := positiveMilliseconds(
		"one-to-one ring timeout",
		s.OneToOneTimeoutMilliseconds,
	)
	if err != nil {
		return RingTimeoutConfiguration{}, err
	}
	group, err := positiveMilliseconds(
		"group ring timeout",
		s.GroupTimeoutMilliseconds,
	)
	if err != nil {
		return RingTimeoutConfiguration{}, err
	}
	policy, err := callsession.NewRingTimeoutPolicy(oneToOne, group)
	if err != nil {
		return RingTimeoutConfiguration{}, err
	}
	return RingTimeoutConfiguration{
		SweepInterval: sweepInterval,
		DomainPolicy:  policy,
	}, nil
}

func positiveMilliseconds(name string, milliseconds int) (time.Duration, error) {
	if milliseconds <= 0 {
		return 0, fmt.Errorf("%s must be positive", name)
	}
	if int64(milliseconds) > math.MaxInt64/int64(time.Millisecond) {
		return 0, fmt.Errorf("%s exceeds time.Duration", name)
	}
	return time.Duration(milliseconds) * time.Millisecond, nil
}
