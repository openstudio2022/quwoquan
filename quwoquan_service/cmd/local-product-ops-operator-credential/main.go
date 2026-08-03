// Command local-product-ops-operator-credential emits one short-lived local
// Product Ops operator JWT for Alpha/Beta/Gamma environment acceptance only.
//
// The token is written to captured stdout and must remain in the invoking
// stackctl process. Prod and every non-local environment require a real RS256
// OIDC operator and are deliberately rejected here.
package main

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
)

func main() {
	environment := strings.ToLower(strings.TrimSpace(os.Getenv("APP_ENV")))
	if environment != "alpha" && environment != "beta" && environment != "gamma" {
		fail("APP_ENV must be alpha, beta, or gamma")
	}
	version, err := strconv.Atoi(strings.TrimSpace(os.Getenv("AUTH_JWT_TOKEN_VERSION")))
	if err != nil {
		fail("AUTH_JWT_TOKEN_VERSION is invalid")
	}
	signer, err := rtauth.NewHS256Signer(rtauth.TokenConfig{
		Secret:       []byte(os.Getenv("AUTH_JWT_SECRET")),
		Issuer:       os.Getenv("AUTH_JWT_ISSUER"),
		Audience:     os.Getenv("AUTH_JWT_AUDIENCE"),
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: version,
		TTL:          15 * time.Minute,
		ClockSkew:    30 * time.Second,
	})
	if err != nil {
		fail(err.Error())
	}
	token, err := signer.Sign(rtauth.TokenSubject{
		AccountID: "operator:content-commercial:" + environment,
		AuthEpoch: 1,
		Scopes: []string{
			"ops.experiment.read", "ops.experiment.write",
			"ops.reco.read", "ops.reco.write", "ops.telemetry.read",
		},
		Roles:     []string{"operator"},
	})
	if err != nil {
		fail(err.Error())
	}
	if strings.TrimSpace(token) == "" || strings.Contains(token, "\n") {
		fail("canonical signer returned an invalid token")
	}
	fmt.Println(token)
}

func fail(detail string) {
	fmt.Fprintln(os.Stderr, "local Product Ops operator credential:", detail)
	os.Exit(2)
}
