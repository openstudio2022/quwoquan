package runtimeobservability

import (
	"testing"

	"github.com/prometheus/client_golang/prometheus/testutil"
)

func TestMQPublishMetrics(t *testing.T) {
	mqPublishTotal.Reset()
	mqPublishDurationSeconds.Reset()

	mqPublishTotal.WithLabelValues("test-topic", "ok").Inc()
	mqPublishDurationSeconds.WithLabelValues("test-topic").Observe(0.05)

	mqPublishTotal.WithLabelValues("test-topic", "error").Inc()

	okVal := testutil.ToFloat64(mqPublishTotal.WithLabelValues("test-topic", "ok"))
	if okVal != 1 {
		t.Errorf("expected ok=1, got %v", okVal)
	}
	errVal := testutil.ToFloat64(mqPublishTotal.WithLabelValues("test-topic", "error"))
	if errVal != 1 {
		t.Errorf("expected error=1, got %v", errVal)
	}

	count := testutil.CollectAndCount(mqPublishDurationSeconds)
	if count == 0 {
		t.Error("expected mqPublishDurationSeconds to have samples")
	}
}

func TestMQConsumeMetrics(t *testing.T) {
	mqConsumeTotal.Reset()
	mqConsumeDurationSeconds.Reset()

	mqConsumeTotal.WithLabelValues("test-topic", "test-group", "ok").Inc()
	mqConsumeTotal.WithLabelValues("test-topic", "test-group", "ok").Inc()
	mqConsumeTotal.WithLabelValues("test-topic", "test-group", "error").Inc()
	mqConsumeDurationSeconds.WithLabelValues("test-topic", "test-group").Observe(0.1)

	okVal := testutil.ToFloat64(mqConsumeTotal.WithLabelValues("test-topic", "test-group", "ok"))
	if okVal != 2 {
		t.Errorf("expected ok=2, got %v", okVal)
	}
	errVal := testutil.ToFloat64(mqConsumeTotal.WithLabelValues("test-topic", "test-group", "error"))
	if errVal != 1 {
		t.Errorf("expected error=1, got %v", errVal)
	}
}
