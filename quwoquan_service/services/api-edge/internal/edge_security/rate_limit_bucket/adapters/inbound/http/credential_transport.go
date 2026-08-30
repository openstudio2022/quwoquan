package httpadapter

import (
	"context"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
)

type credentialContextKey struct{}
type ownerProxyCancellationContextKey struct{}

type verifiedCredential struct {
	authorization string
	deviceTicket  string
}

// PreserveCredentialTransport captures credential bytes before auth middleware
// removes them. The proxy can only restore them after that middleware and the
// generated operation guard have succeeded, so invalid credentials can never be
// relayed to an owner service.
func PreserveCredentialTransport(next http.Handler) http.Handler {
	return http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		credential := verifiedCredential{
			authorization: strings.TrimSpace(request.Header.Get("Authorization")),
			deviceTicket:  strings.TrimSpace(request.Header.Get(rtauth.DeviceTicketHeader)),
		}
		contextWithCredential := context.WithValue(
			request.Context(),
			credentialContextKey{},
			credential,
		)
		// Save the request cancellation source before the generated operation
		// guard adds the owner's reliability deadline. The public edge proxy owns
		// a wider network budget, but must still stop immediately when the client
		// disconnects or the HTTP server shuts down.
		contextWithProxyCancellation := context.WithValue(
			contextWithCredential,
			ownerProxyCancellationContextKey{},
			request.Context(),
		)
		next.ServeHTTP(response, request.WithContext(contextWithProxyCancellation))
	})
}

func ownerProxyCancellationContext(ctx context.Context) (context.Context, bool) {
	if ctx == nil {
		return nil, false
	}
	parent, ok := ctx.Value(ownerProxyCancellationContextKey{}).(context.Context)
	return parent, ok && parent != nil
}

func restoreVerifiedCredential(request *http.Request) {
	credential, ok := request.Context().Value(credentialContextKey{}).(verifiedCredential)
	if !ok {
		return
	}
	request.Header.Del("Authorization")
	request.Header.Del(rtauth.DeviceTicketHeader)
	if credential.authorization != "" {
		request.Header.Set("Authorization", credential.authorization)
	}
	if credential.deviceTicket != "" {
		request.Header.Set(rtauth.DeviceTicketHeader, credential.deviceTicket)
	}
}
