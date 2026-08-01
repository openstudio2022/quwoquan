// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-001
package assistant_run_test

import (
	"errors"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	dto "github.com/prometheus/client_model/go"
	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	runruntime "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

func TestAssistantRunLifecycleMetricsUseBoundedCanonicalLabels(t *testing.T) {
	now := time.Date(2026, 7, 31, 12, 0, 0, 0, time.UTC)
	run := newDurableRun(t, now)

	transitionBefore := gatheredCounterValue(t, "assistant_run_state_transition_total", map[string]string{
		"from": "accepted",
		"to":   "orienting",
	})
	if err := run.Transition(
		generated.AssistantRunStateOrienting,
		"",
		now.Add(time.Second),
	); err != nil {
		t.Fatal(err)
	}

	closureBefore := gatheredCounterValue(t, "assistant_run_item_closure_total", map[string]string{
		"kind":   "evidence",
		"status": "completed",
	})
	if err := run.BeginItem(
		"evidence:metric",
		generated.AssistantRunItemKindEvidence,
		"research",
		"validated source",
		map[string]any{"sourceCount": 1},
		now.Add(2*time.Second),
	); err != nil {
		t.Fatal(err)
	}
	if err := run.CompleteItem(
		"evidence:metric",
		generated.AssistantRunItemStatusCompleted,
		[]string{"artifact:metric"},
		"",
		now.Add(3*time.Second),
	); err != nil {
		t.Fatal(err)
	}

	rejectedBefore := gatheredCounterValue(t, "assistant_run_completion_rejected_total", map[string]string{
		"reason": "verdict",
	})
	if err := run.AcceptVerification(
		runruntime.VerificationVerdict{Accepted: false},
		now.Add(4*time.Second),
	); !errors.Is(err, runruntime.ErrCompletionRejected) {
		t.Fatalf("AcceptVerification() error = %v", err)
	}

	assertCounterIncremented(
		t,
		"state transition",
		transitionBefore,
		gatheredCounterValue(t, "assistant_run_state_transition_total", map[string]string{
			"from": "accepted",
			"to":   "orienting",
		}),
	)
	assertCounterIncremented(
		t,
		"item closure",
		closureBefore,
		gatheredCounterValue(t, "assistant_run_item_closure_total", map[string]string{
			"kind":   "evidence",
			"status": "completed",
		}),
	)
	assertCounterIncremented(
		t,
		"completion rejection",
		rejectedBefore,
		gatheredCounterValue(t, "assistant_run_completion_rejected_total", map[string]string{
			"reason": "verdict",
		}),
	)
}

func assertCounterIncremented(t *testing.T, name string, before float64, after float64) {
	t.Helper()
	if after != before+1 {
		t.Fatalf("%s metric delta = %v, want 1", name, after-before)
	}
}

func gatheredCounterValue(
	t *testing.T,
	name string,
	labels map[string]string,
) float64 {
	t.Helper()
	families, err := prometheus.DefaultGatherer.Gather()
	if err != nil {
		t.Fatalf("Gather() error = %v", err)
	}
	for _, family := range families {
		if family.GetName() != name {
			continue
		}
		for _, metric := range family.GetMetric() {
			if metricLabelsMatch(metric.GetLabel(), labels) {
				return metric.GetCounter().GetValue()
			}
		}
	}
	return 0
}

func metricLabelsMatch(
	pairs []*dto.LabelPair,
	want map[string]string,
) bool {
	if len(pairs) != len(want) {
		return false
	}
	for _, pair := range pairs {
		if want[pair.GetName()] != pair.GetValue() {
			return false
		}
	}
	return true
}
