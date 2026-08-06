package call_session

import (
	"fmt"
	"time"

	"quwoquan_service/services/rtc-service/internal/rtc/call_session/domain/model"
)

// RingTimeoutPolicy owns the CallSession ring-timeout invariant. Runtime
// configuration may choose the durations, but application and transport code
// must consume this validated domain value instead of defining local defaults.
type RingTimeoutPolicy struct {
	oneToOne time.Duration
	group    time.Duration
}

func NewRingTimeoutPolicy(
	oneToOne time.Duration,
	group time.Duration,
) (RingTimeoutPolicy, error) {
	policy := RingTimeoutPolicy{oneToOne: oneToOne, group: group}
	if err := policy.validate(); err != nil {
		return RingTimeoutPolicy{}, err
	}
	return policy, nil
}

func (p RingTimeoutPolicy) validate() error {
	if p.oneToOne <= 0 {
		return fmt.Errorf("one-to-one ring timeout must be positive")
	}
	if p.group <= 0 {
		return fmt.Errorf("group ring timeout must be positive")
	}
	if p.oneToOne > p.group {
		return fmt.Errorf(
			"one-to-one ring timeout %s must not exceed group ring timeout %s",
			p.oneToOne,
			p.group,
		)
	}
	return nil
}

func (p RingTimeoutPolicy) OneToOne() time.Duration {
	return p.oneToOne
}

func (p RingTimeoutPolicy) Group() time.Duration {
	return p.group
}

func (p RingTimeoutPolicy) For(session *model.CallSession) time.Duration {
	if session != nil && session.MaxParticipants > model.MaxParticipants1v1 {
		return p.group
	}
	return p.oneToOne
}
