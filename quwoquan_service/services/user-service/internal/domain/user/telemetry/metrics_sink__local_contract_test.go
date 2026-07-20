package telemetry

import (
	"testing"
	"time"
)

type recordingUserMetricsSink struct {
	profileReadLatencies []float64
	personaLatencies     []float64
	profileCounters      map[string]int
	personaCounters      map[string]int
}

func newRecordingUserMetricsSink() *recordingUserMetricsSink {
	return &recordingUserMetricsSink{
		profileCounters: map[string]int{},
		personaCounters: map[string]int{},
	}
}

func (sink *recordingUserMetricsSink) ObserveProfileSubjectPublicReadLatency(
	milliseconds float64,
) {
	sink.profileReadLatencies = append(sink.profileReadLatencies, milliseconds)
}

func (sink *recordingUserMetricsSink) IncrementProfileSubjectCounter(
	metricName string,
) {
	sink.profileCounters[metricName]++
}

func (sink *recordingUserMetricsSink) ObservePersonaSwitchLatency(
	milliseconds float64,
) {
	sink.personaLatencies = append(sink.personaLatencies, milliseconds)
}

func (sink *recordingUserMetricsSink) IncrementPersonaRolloutCounter(
	metricName string,
) {
	sink.personaCounters[metricName]++
}

func TestProfileSubjectMetrics_ForwardsSamplesAndPreservesSnapshot(
	t *testing.T,
) {
	sink := newRecordingUserMetricsSink()
	metrics := &ProfileSubjectMetrics{}
	metrics.SetSink(sink)

	metrics.RecordPublicRead(15 * time.Millisecond)
	metrics.RecordVisibilityNotFound()
	metrics.RecordSyncScopeSubmit()

	if len(sink.profileReadLatencies) != 1 ||
		sink.profileReadLatencies[0] != 15 {
		t.Fatalf(
			"profile read latency samples = %v, want [15]",
			sink.profileReadLatencies,
		)
	}
	for _, name := range []string{
		MetricProfileSubjectVisibilityNotFoundCount,
		MetricProfileSubjectSyncScopeSubmitCount,
	} {
		if sink.profileCounters[name] != 1 {
			t.Errorf("forwarded profile counter %q = %d, want 1", name, sink.profileCounters[name])
		}
	}
	if got := metrics.Snapshot()[MetricProfileSubjectPublicReadLatencyMs]; got != 15 {
		t.Errorf("snapshot profile latency = %v, want 15", got)
	}
}

func TestPersonaRolloutMetrics_ForwardsSamplesAndPreservesSnapshot(
	t *testing.T,
) {
	sink := newRecordingUserMetricsSink()
	metrics := &PersonaRolloutMetrics{}
	metrics.SetSink(sink)

	metrics.RecordSwitchLatency(21 * time.Millisecond)
	metrics.RecordAttributionMismatch()
	metrics.RecordPublicLeakage()
	metrics.RecordMigrationFailure()

	if len(sink.personaLatencies) != 1 || sink.personaLatencies[0] != 21 {
		t.Fatalf("persona latency samples = %v, want [21]", sink.personaLatencies)
	}
	for _, name := range []string{
		MetricPersonaAttributionMismatchCount,
		MetricPersonaPublicLeakageCount,
		MetricPersonaMigrationFailedCount,
	} {
		if sink.personaCounters[name] != 1 {
			t.Errorf("forwarded persona counter %q = %d, want 1", name, sink.personaCounters[name])
		}
	}
	if got := metrics.Snapshot()[MetricPersonaSwitchLatencyMs]; got != 21 {
		t.Errorf("snapshot persona latency = %v, want 21", got)
	}
}
