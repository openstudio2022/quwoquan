package mongo

import (
	"testing"

	"github.com/prometheus/client_golang/prometheus/testutil"
)

func TestMongoCommandMetrics(t *testing.T) {
	mongoCommandTotal.Reset()
	mongoCommandDurationSeconds.Reset()

	mongoCommandTotal.WithLabelValues("find", "testdb", "ok").Inc()
	mongoCommandTotal.WithLabelValues("insert", "testdb", "ok").Inc()
	mongoCommandTotal.WithLabelValues("find", "testdb", "error").Inc()
	mongoCommandDurationSeconds.WithLabelValues("find", "testdb").Observe(0.05)

	findOk := testutil.ToFloat64(mongoCommandTotal.WithLabelValues("find", "testdb", "ok"))
	if findOk != 1 {
		t.Errorf("expected find ok=1, got %v", findOk)
	}
	findErr := testutil.ToFloat64(mongoCommandTotal.WithLabelValues("find", "testdb", "error"))
	if findErr != 1 {
		t.Errorf("expected find error=1, got %v", findErr)
	}
}

func TestMongoPoolMetrics(t *testing.T) {
	mongoPoolInUse.Set(0)
	mongoPoolIdle.Set(0)

	createdBefore := testutil.ToFloat64(mongoPoolCreatedTotal)
	closedBefore := testutil.ToFloat64(mongoPoolClosedTotal)

	mongoPoolCreatedTotal.Inc()
	mongoPoolIdle.Inc()

	mongoPoolInUse.Inc()
	mongoPoolIdle.Dec()

	created := testutil.ToFloat64(mongoPoolCreatedTotal)
	if created != createdBefore+1 {
		t.Errorf("expected pool_created to increase by 1 (before %v, got %v)", createdBefore, created)
	}
	inUse := testutil.ToFloat64(mongoPoolInUse)
	if inUse != 1 {
		t.Errorf("expected pool_in_use=1, got %v", inUse)
	}
	// closed counter unchanged in this scenario
	if testutil.ToFloat64(mongoPoolClosedTotal) != closedBefore {
		t.Errorf("expected pool_closed unchanged, got %v vs before %v",
			testutil.ToFloat64(mongoPoolClosedTotal), closedBefore)
	}
}
