package eventstore

import (
	"testing"

	"github.com/prometheus/client_golang/prometheus/testutil"
)

func TestEventstorePrometheusMetricsExist(t *testing.T) {
	// Verify that the promauto counters are registered and can be incremented.
	eventstoreAppendTotal.WithLabelValues("test_aggregate", "ok").Inc()
	eventstoreAppendTotal.WithLabelValues("test_aggregate", "error").Inc()
	eventstorePublishFailures.WithLabelValues("test_aggregate").Inc()

	ok := testutil.ToFloat64(eventstoreAppendTotal.WithLabelValues("test_aggregate", "ok"))
	if ok < 1 {
		t.Errorf("eventstore_append_total{status=ok}: expected >= 1, got %v", ok)
	}

	errVal := testutil.ToFloat64(eventstoreAppendTotal.WithLabelValues("test_aggregate", "error"))
	if errVal < 1 {
		t.Errorf("eventstore_append_total{status=error}: expected >= 1, got %v", errVal)
	}

	pubFail := testutil.ToFloat64(eventstorePublishFailures.WithLabelValues("test_aggregate"))
	if pubFail < 1 {
		t.Errorf("eventstore_publish_failures_total: expected >= 1, got %v", pubFail)
	}
}
