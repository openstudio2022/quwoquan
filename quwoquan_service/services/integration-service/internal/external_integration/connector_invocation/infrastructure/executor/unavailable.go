package executor

import (
	"context"
	"errors"

	invocationapp "quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/application"
)

var ErrCapabilityExecutorUnavailable = errors.New(
	"connector capability executor is unavailable",
)

// UnavailableCapabilityExecutor prevents an absent Provider adapter from
// becoming an in-memory or no-op success path in production composition.
type UnavailableCapabilityExecutor struct{}

func (UnavailableCapabilityExecutor) Execute(
	context.Context,
	invocationapp.CapabilityExecution,
) (invocationapp.CapabilityOutcome, error) {
	return invocationapp.CapabilityOutcome{}, ErrCapabilityExecutorUnavailable
}

var _ invocationapp.CapabilityExecutor = UnavailableCapabilityExecutor{}
