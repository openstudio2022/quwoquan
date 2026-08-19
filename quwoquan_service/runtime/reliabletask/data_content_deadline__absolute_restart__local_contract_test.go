// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-010.t1
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-010.t2

package reliabletask

import (
	"testing"
	"time"
)

func TestRemainingDataContentFleetBatchDurationNeverRenewsFrozenDeadline(t *testing.T) {
	deadline := time.Unix(2_000_000_000, 0)
	first, err := RemainingDataContentFleetBatchDuration(
		deadline.Unix(),
		deadline.Add(-10*time.Minute),
	)
	if err != nil {
		t.Fatal(err)
	}
	restarted, err := RemainingDataContentFleetBatchDuration(
		deadline.Unix(),
		deadline.Add(-time.Minute),
	)
	if err != nil {
		t.Fatal(err)
	}
	if first != 10*time.Minute || restarted != time.Minute || restarted >= first {
		t.Fatalf(
			"frozen deadline renewed across restart: first=%s restarted=%s",
			first,
			restarted,
		)
	}
}

func TestRemainingDataContentFleetBatchDurationRejectsExpiredRestart(t *testing.T) {
	deadline := time.Unix(2_000_000_000, 0)
	for _, now := range []time.Time{deadline, deadline.Add(time.Second)} {
		if _, err := RemainingDataContentFleetBatchDuration(deadline.Unix(), now); err == nil {
			t.Fatalf("expired deadline admitted at %s", now)
		}
	}
}

func TestRemainingDataContentFleetBatchDurationRejectsUnfrozenDeadline(t *testing.T) {
	for _, deadlineEpochSeconds := range []int64{0, -1} {
		if _, err := RemainingDataContentFleetBatchDuration(
			deadlineEpochSeconds,
			time.Unix(1_000_000_000, 0),
		); err == nil {
			t.Fatalf("deadline=%d was admitted as frozen", deadlineEpochSeconds)
		}
	}
}
