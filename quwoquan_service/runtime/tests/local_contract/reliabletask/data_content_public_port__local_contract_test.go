// spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-001
package reliabletask_test

import (
	"context"
	"strings"
	"testing"

	"quwoquan_service/runtime/reliabletask"
)

func TestDataContentPublicPortIsReachableFromCanonicalLocalContract(t *testing.T) {
	job := reliabletask.DataContentJob{
		EntityRef:            "entity/地点/景区/001",
		Carrier:              "homepage",
		SourceRevision:       "sha256:" + strings.Repeat("a", 64),
		JobID:                "job-001",
		ExecutionID:          "20260722--runtime-test-directory--cn-zhejiang--001",
		Ref:                  "entity/地点/景区/001",
		Stage:                "author",
		PartitionKey:         "entity/地点/景区/001",
		MaxAttempts:          3,
		JobSetEnvelopeDigest: "sha256:" + strings.Repeat("e", 64),
		JobSetDigest:         "sha256:" + strings.Repeat("f", 64),
		ActualTaskDigest:     "sha256:" + strings.Repeat("f", 64),
	}
	key, err := job.ExpectedIdempotencyKey()
	if err != nil {
		t.Fatalf("runtime public data-content port is not reachable: %v", err)
	}
	job.IdempotencyKey = key
	if _, err := job.ValidateIdentity(); err != nil {
		t.Fatalf("runtime public identity contract drifted: %v", err)
	}

	var _ reliabletask.DataContentExecutor = reliabletask.DataContentExecutorFunc(
		func(context.Context, reliabletask.DataContentWorkItem) (reliabletask.DataContentExecutionResult, error) {
			return reliabletask.DataContentExecutionResult{}, nil
		},
	)
}
