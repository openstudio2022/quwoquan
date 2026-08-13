package health

import (
	"context"
	"errors"
	"slices"
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
