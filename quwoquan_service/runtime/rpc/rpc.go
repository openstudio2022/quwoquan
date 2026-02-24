package runtimerpc

import "context"

// RPCMetadata carries normalized runtime context in RPC calls.
type RPCMetadata struct {
	TraceID    string
	RequestID  string
	SessionID  string
	PageID     string
	UserID     string
	PersonaID  string
	Source     string
	Service    string
	InstanceID string
}

// UnaryHandler describes unified unary call signature.
type UnaryHandler func(ctx context.Context, req any) (any, error)

// UnaryInterceptor wraps unary calls for governance/observability binding.
type UnaryInterceptor func(ctx context.Context, method string, req any, next UnaryHandler) (any, error)

// ChainUnaryInterceptors composes interceptors in declaration order.
func ChainUnaryInterceptors(interceptors ...UnaryInterceptor) UnaryInterceptor {
	return func(ctx context.Context, method string, req any, next UnaryHandler) (any, error) {
		wrapped := next
		for i := len(interceptors) - 1; i >= 0; i-- {
			current := interceptors[i]
			downstream := wrapped
			wrapped = func(c context.Context, r any) (any, error) {
				return current(c, method, r, downstream)
			}
		}
		return wrapped(ctx, req)
	}
}
