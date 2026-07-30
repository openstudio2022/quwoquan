package httpadapter

import (
	"context"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
)

type credentialContextKey struct{}

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
		next.ServeHTTP(response, request.WithContext(contextWithCredential))
	})
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
