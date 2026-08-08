package authority

import (
	"context"
	"errors"

	invocationapp "quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/application"
)

var ErrExecutionAuthorityUnavailable = errors.New(
	"connector invocation execution authority is unavailable",
)

// UnavailableExecutionAuthority is the production fail-closed binding until a
// release supplies the real permit consumer and Provider probe. It makes the
// missing dependency explicit and guarantees no executor side effect occurs.
type UnavailableExecutionAuthority struct{}

func (UnavailableExecutionAuthority) AuthorizeExecution(
	context.Context,
	invocationapp.ExecutionAuthorityInput,
) (invocationapp.ExecutionPermit, error) {
	return invocationapp.ExecutionPermit{}, ErrExecutionAuthorityUnavailable
}

var _ invocationapp.ExecutionAuthority = UnavailableExecutionAuthority{}
