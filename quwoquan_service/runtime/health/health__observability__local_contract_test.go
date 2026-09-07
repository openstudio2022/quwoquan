package health

import (
	"context"
	"errors"
	"slices"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus/testutil"
)

func TestCheckerPublishesNamedHealthMetrics(t *testing.T) {
	t.Parallel()

	checker := NewChecker()
	checker.Register("content_projection_contract_test_ok", func(context.Context) error {
		return nil
	})
	checker.Register("content_projection_contract_test_failed", func(context.Context) error {
		return errors.New("checkpoint stalled")
	})

	result := checker.Check(context.Background())

	if result.Status != "degraded" {
		t.Fatalf("status=%q want degraded", result.Status)
	}
	if !slices.Equal(
		result.FailedChecks,
		[]string{"content_projection_contract_test_failed"},
	) {
		t.Fatalf("failedChecks=%v", result.FailedChecks)
	}
	if got := testutil.ToFloat64(
		healthCheckStatus.WithLabelValues("content_projection_contract_test_ok"),
	); got != 1 {
		t.Fatalf("healthy metric=%v want 1", got)
	}
	if got := testutil.ToFloat64(
		healthCheckStatus.WithLabelValues("content_projection_contract_test_failed"),
	); got != 0 {
		t.Fatalf("failed metric=%v want 0", got)
	}
	if got := testutil.ToFloat64(
		healthCheckLastSuccess.WithLabelValues("content_projection_contract_test_ok"),
	); got <= 0 {
		t.Fatalf("last success timestamp=%v want >0", got)
	}
}

func TestCheckerHonorsDependencySpecificTimeout(t *testing.T) {
	checker := NewChecker()
	checker.RegisterWithTimeout(
		"mongodb",
		20*time.Millisecond,
		func(ctx context.Context) error {
			select {
			case <-time.After(5 * time.Millisecond):
				return nil
			case <-ctx.Done():
				return ctx.Err()
			}
		},
	)

	result := checker.Check(context.Background())

	if result.Status != "ok" {
		t.Fatalf("status=%q checks=%v want ok", result.Status, result.Checks)
	}
}

func TestCheckerFailsClosedOnDuplicateNamedCheck(t *testing.T) {
	checker := NewChecker()
	var firstCalls atomic.Int32
	var duplicateCalls atomic.Int32

	checker.Register("mongodb.authority", func(context.Context) error {
		firstCalls.Add(1)
		return nil
	})
	checker.Register("mongodb.authority", func(context.Context) error {
		duplicateCalls.Add(1)
		return nil
	})

	result := checker.Check(context.Background())

	if result.Status != "degraded" {
		t.Fatalf("status=%q checks=%v want degraded", result.Status, result.Checks)
	}
	if !slices.Equal(result.FailedChecks, []string{"mongodb.authority"}) {
		t.Fatalf("failedChecks=%v", result.FailedChecks)
	}
	if got, want := result.Checks["mongodb.authority"], "registration error: duplicate check name"; got != want {
		t.Fatalf("check diagnostic=%q want %q", got, want)
	}
	if got := firstCalls.Load(); got != 1 {
		t.Fatalf("first check calls=%d want 1", got)
	}
	if got := duplicateCalls.Load(); got != 0 {
		t.Fatalf("duplicate check calls=%d want 0", got)
	}
}

func TestCheckerExecutesDistinctNamedStorageSlots(t *testing.T) {
	checker := NewChecker()
	var authorityCalls atomic.Int32
	var checkpointCalls atomic.Int32

	checker.Register("mongodb.authority", func(context.Context) error {
		authorityCalls.Add(1)
		return nil
	})
	checker.Register("mongodb.checkpoint", func(context.Context) error {
		checkpointCalls.Add(1)
		return nil
	})

	result := checker.Check(context.Background())

	if result.Status != "ok" {
		t.Fatalf("status=%q checks=%v want ok", result.Status, result.Checks)
	}
	if got := authorityCalls.Load(); got != 1 {
		t.Fatalf("authority check calls=%d want 1", got)
	}
	if got := checkpointCalls.Load(); got != 1 {
		t.Fatalf("checkpoint check calls=%d want 1", got)
	}
	if got := result.Checks["mongodb.authority"]; got != "ok" {
		t.Fatalf("authority result=%q want ok", got)
	}
	if got := result.Checks["mongodb.checkpoint"]; got != "ok" {
		t.Fatalf("checkpoint result=%q want ok", got)
	}
}

func TestCheckerReportsDependencySpecificTimeout(t *testing.T) {
	checker := NewChecker()
	checker.RegisterWithTimeout(
		"mongodb.timeout_contract_test",
		5*time.Millisecond,
		func(ctx context.Context) error {
			<-ctx.Done()
			return ctx.Err()
		},
	)

	result := checker.Check(context.Background())

	if result.Status != "degraded" {
		t.Fatalf("status=%q checks=%v want degraded", result.Status, result.Checks)
	}
	if !slices.Equal(
		result.FailedChecks,
		[]string{"mongodb.timeout_contract_test"},
	) {
		t.Fatalf("failedChecks=%v", result.FailedChecks)
	}
	if got := result.Checks["mongodb.timeout_contract_test"]; got != context.DeadlineExceeded.Error() {
		t.Fatalf("timeout result=%q want %q", got, context.DeadlineExceeded.Error())
	}
}

func TestCheckerSupportsConcurrentRegistrationAndChecks(t *testing.T) {
	checker := NewChecker()
	start := make(chan struct{})
	var workers sync.WaitGroup

	for index := 0; index < 16; index++ {
		name := "concurrent." + string(rune('a'+index))
		workers.Add(2)
		go func() {
			defer workers.Done()
			<-start
			checker.Register(name, func(context.Context) error { return nil })
		}()
		go func() {
			defer workers.Done()
			<-start
			result := checker.Check(context.Background())
			if result.Status != "ok" {
				t.Errorf("status=%q checks=%v want ok", result.Status, result.Checks)
			}
		}()
	}

	close(start)
	workers.Wait()

	result := checker.Check(context.Background())
	if result.Status != "ok" {
		t.Fatalf("final status=%q checks=%v want ok", result.Status, result.Checks)
	}
	if got, want := len(result.Checks), 16; got != want {
		t.Fatalf("registered checks=%d want %d", got, want)
	}
}
