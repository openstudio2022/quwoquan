// Command local-filter-catalog-credential emits one short-lived local service JWT.
//
// It is an Ops-only bridge to the canonical runtime signer. The token is
// written to captured stdout and must be injected only into the publisher
// child environment; callers must never persist or log it.
package main

import (
	"context"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
)

func main() {
	version, err := strconv.Atoi(strings.TrimSpace(os.Getenv("AUTH_JWT_TOKEN_VERSION")))
	if err != nil {
		fail("AUTH_JWT_TOKEN_VERSION is invalid")
	}
	provider, err := rtauth.NewHS256ServiceAuthorizationProvider(
		rtauth.TokenConfig{
			Secret:       []byte(os.Getenv("AUTH_JWT_SECRET")),
			Issuer:       os.Getenv("AUTH_JWT_ISSUER"),
			Audience:     os.Getenv("AUTH_JWT_AUDIENCE"),
			Type:         rtauth.TokenTypeAccess,
			TokenVersion: version,
			TTL:          30 * time.Minute,
			ClockSkew:    30 * time.Second,
		},
		"qwq-data",
		[]string{"content.filter_catalog.manage"},
	)
	if err != nil {
		fail(err.Error())
	}
	header, err := provider.AuthorizationHeader(context.Background())
	if err != nil {
		fail(err.Error())
	}
	token := strings.TrimPrefix(header, "Bearer ")
	if token == header || strings.TrimSpace(token) == "" {
		fail("canonical service provider returned an invalid authorization header")
	}
	fmt.Println(token)
}

func fail(detail string) {
	fmt.Fprintln(os.Stderr, "local service credential:", detail)
	os.Exit(2)
}
