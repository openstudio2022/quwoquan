package telemetry

import (
	"testing"
	"time"
)

type recordingSink struct {
	commandLatencies    []float64
	listLatencies       []float64
	projectionLatencies []float64
	counters            map[string]int
}

func (sink *recordingSink) ObserveCommandLatency(milliseconds float64) {
	sink.commandLatencies = append(sink.commandLatencies, milliseconds)
}

func (sink *recordingSink) ObserveListLatency(milliseconds float64) {
	sink.listLatencies = append(sink.listLatencies, milliseconds)
}

func (sink *recordingSink) ObserveCounterProjectionLag(milliseconds float64) {
	sink.projectionLatencies = append(sink.projectionLatencies, milliseconds)
}

func (sink *recordingSink) IncrementCounter(metricName string) {
	sink.counters[metricName]++
}

func TestMetrics_ForwardsProductionSamplesAndPreservesSnapshot(t *testing.T) {
	sink := &recordingSink{counters: map[string]int{}}
	metrics := &Metrics{}
	metrics.SetSink(sink)

	metrics.RecordCommandLatency(12 * time.Millisecond)
	metrics.RecordListLatency(34 * time.Millisecond)
	metrics.RecordCounterProjectionLag(56 * time.Millisecond)
	metrics.RecordDuplicateCommand()
	metrics.RecordBlockRejection()
	metrics.RecordCounterMismatch()
	metrics.RecordPageDrift()
	metrics.RecordFilterMismatch()
	metrics.RecordCapabilityMismatch()

	if len(sink.commandLatencies) != 1 || sink.commandLatencies[0] != 12 {
		t.Fatalf("command latency samples = %v, want [12]", sink.commandLatencies)
	}
	if len(sink.listLatencies) != 1 || sink.listLatencies[0] != 34 {
		t.Fatalf("list latency samples = %v, want [34]", sink.listLatencies)
	}
	if len(sink.projectionLatencies) != 1 || sink.projectionLatencies[0] != 56 {
		t.Fatalf(
			"projection latency samples = %v, want [56]",
			sink.projectionLatencies,
		)
	}
	for _, name := range []string{
		MetricDuplicateCommandCount,
		MetricBlockRejectionCount,
		MetricCounterMismatchCount,
		MetricPageDriftCount,
		MetricFilterMismatchCount,
		MetricCapabilityMismatch,
	} {
		if sink.counters[name] != 1 {
			t.Errorf("forwarded counter %q = %d, want 1", name, sink.counters[name])
		}
	}

	snapshot := metrics.Snapshot()
	if snapshot[MetricCommandLatencyMs] != 12 {
		t.Errorf("snapshot command latency = %v, want 12", snapshot[MetricCommandLatencyMs])
	}
	if snapshot[MetricListLatencyMs] != 34 {
		t.Errorf("snapshot list latency = %v, want 34", snapshot[MetricListLatencyMs])
	}
	if snapshot[MetricCounterProjectionLagMs] != 56 {
		t.Errorf(
			"snapshot counter projection lag = %v, want 56",
			snapshot[MetricCounterProjectionLagMs],
		)
	}
	if snapshot[MetricCapabilityMismatch] != 1 {
		t.Errorf(
			"snapshot capability mismatch = %v, want 1",
			snapshot[MetricCapabilityMismatch],
		)
	}
}

func TestMetrics_ClampsNonPositiveDurationsBeforeForwarding(t *testing.T) {
	sink := &recordingSink{counters: map[string]int{}}
	metrics := &Metrics{}
	metrics.SetSink(sink)

	metrics.RecordCommandLatency(0)
	metrics.RecordListLatency(-time.Millisecond)
	metrics.RecordCounterProjectionLag(0)

	if got := sink.commandLatencies[0]; got != 0.001 {
		t.Errorf("forwarded command latency = %v, want 0.001", got)
	}
	if got := sink.listLatencies[0]; got != 0.001 {
		t.Errorf("forwarded list latency = %v, want 0.001", got)
	}
	if got := sink.projectionLatencies[0]; got != 0.001 {
		t.Errorf("forwarded projection latency = %v, want 0.001", got)
	}
}
