package eventrecord

import (
	"context"
	"errors"

	eventapplication "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
)

// Reporter is the RecoveryFailure outbound adapter to the EventRecord facade.
type Reporter struct {
	runtimeLogs *eventapplication.RuntimeLogService
}

func NewReporter(runtimeLogs *eventapplication.RuntimeLogService) (*Reporter, error) {
	if runtimeLogs == nil {
		return nil, errors.New("RecoveryFailure EventRecord runtime-log facade is required")
	}
	return &Reporter{runtimeLogs: runtimeLogs}, nil
}

func (reporter *Reporter) ReportRecoveryFailure(
	ctx context.Context,
	batchKey string,
	fields map[string]string,
) (eventapplication.EventBatchAck, error) {
	return reporter.runtimeLogs.ReportRecoveryFailure(ctx, batchKey, fields)
}
