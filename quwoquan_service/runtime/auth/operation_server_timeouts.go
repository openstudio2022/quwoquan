package auth

import "time"

const (
	// operationWriteHeadroom keeps the transport ceiling strictly above the
	// widest contract budget so the declared reliability.timeout_ms is the
	// value that actually governs a response. A hand-written WriteTimeout that
	// preempts the contract turns the transport into a second truth source.
	operationWriteHeadroom = 10 * time.Second
	// operationReadHeaderTimeout bounds request header reads. Header reading
	// happens before route matching, so no operation contract can describe it.
	operationReadHeaderTimeout = 5 * time.Second
	// operationIdleTimeout bounds keep-alive reuse between requests. It is a
	// connection-pooling property, not an operation property.
	operationIdleTimeout = 120 * time.Second
)

// HTTPServerTimeouts carries the transport ceilings of one HTTP server.
type HTTPServerTimeouts struct {
	ReadHeader time.Duration
	Write      time.Duration
	Idle       time.Duration
}

// ContractHTTPServerTimeouts derives one server's transport ceilings from the
// generated operation descriptors that server actually serves. Composition
// roots must call this instead of writing their own durations: the widest
// operation budget is a ContractGraph fact, and duplicating it as a literal is
// how a service ends up cutting a response before its declared deadline.
//
// Write is sized against the widest unary budget only. Go applies WriteTimeout
// once per connection and never refreshes it per flush, so a streaming route
// cannot live under it at all; those routes clear their own write deadline and
// are bounded by their declared stream budget instead. Letting a connection
// lifetime measured in minutes set the ceiling would silently relax the
// backstop for every unary operation on the same server.
func ContractHTTPServerTimeouts(
	descriptors []OperationSecurityDescriptor,
) HTTPServerTimeouts {
	return HTTPServerTimeouts{
		ReadHeader: operationReadHeaderTimeout,
		Write:      MaxOperationTimeout(descriptors) + operationWriteHeadroom,
		Idle:       operationIdleTimeout,
	}
}

// MaxOperationTimeout returns the widest declared unary reliability.timeout_ms
// in the descriptor set. Streaming descriptors are excluded: their
// TimeoutMilliseconds is a derived connection lifetime, not a response budget.
// An empty or budgetless set is a wiring bug: validate already rejects a
// commercial operation without a positive timeout, so reaching here with none
// means the composition root passed the wrong table.
func MaxOperationTimeout(
	descriptors []OperationSecurityDescriptor,
) time.Duration {
	widest := 0
	for _, descriptor := range descriptors {
		if descriptor.StreamBudget != nil {
			continue
		}
		if descriptor.TimeoutMilliseconds > widest {
			widest = descriptor.TimeoutMilliseconds
		}
	}
	if widest <= 0 {
		panic("operation descriptor set declares no positive unary timeout budget")
	}
	return time.Duration(widest) * time.Millisecond
}
