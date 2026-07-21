package application

import (
	"testing"

	"github.com/prometheus/client_golang/prometheus/testutil"
)

func TestRecordAssistantMentionedConsumerDLQIncrementsRecoverableDeadLetterMetric(t *testing.T) {
	before := testutil.ToFloat64(assistantMentionedConsumerDLQTotal)

	RecordAssistantMentionedConsumerDLQ()

	if got := testutil.ToFloat64(assistantMentionedConsumerDLQTotal) - before; got != 1 {
		t.Fatalf("assistant mentioned DLQ metric delta = %v, want 1", got)
	}
}
