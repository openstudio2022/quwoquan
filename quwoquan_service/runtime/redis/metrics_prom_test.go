package redis

import (
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus/testutil"
)

func TestMetricsCollectorBridgesToPrometheus(t *testing.T) {
	mc := NewMetricsCollector([]string{"cache"})

	mc.Record("cache", 5*time.Millisecond, nil)
	mc.Record("cache", 10*time.Millisecond, nil)

	okVal := testutil.ToFloat64(redisOpsTotal.WithLabelValues("cache", "ok"))
	if okVal != 2 {
		t.Errorf("redis_operations_total{status=ok}: expected 2, got %v", okVal)
	}

	errVal := testutil.ToFloat64(redisOpsTotal.WithLabelValues("cache", "error"))
	if errVal != 0 {
		t.Errorf("redis_operations_total{status=error}: expected 0, got %v", errVal)
	}
}

func TestMetricsCollectorRecordsErrors(t *testing.T) {
	mc := NewMetricsCollector([]string{"session"})
	mc.Record("session", 2*time.Millisecond, nil)
	mc.Record("session", 3*time.Millisecond, errForTest)

	okVal := testutil.ToFloat64(redisOpsTotal.WithLabelValues("session", "ok"))
	if okVal != 1 {
		t.Errorf("redis_operations_total{status=ok}: expected 1, got %v", okVal)
	}
	errVal := testutil.ToFloat64(redisOpsTotal.WithLabelValues("session", "error"))
	if errVal != 1 {
		t.Errorf("redis_operations_total{status=error}: expected 1, got %v", errVal)
	}

	snap := mc.Snapshot()
	if snap["session"].TotalOps != 2 {
		t.Errorf("atomic ops: expected 2, got %d", snap["session"].TotalOps)
	}
	if snap["session"].TotalErrs != 1 {
		t.Errorf("atomic errs: expected 1, got %d", snap["session"].TotalErrs)
	}
}

type testError struct{}

func (testError) Error() string { return "test error" }

var errForTest error = testError{}
