// Command acceptance-session issues an ephemeral bearer for the seeded
// local-Gamma acceptance principal. It is an Ops-only process boundary, not an
// HTTP login route or a production authentication bypass.
package main

import (
	"encoding/json"
	"log"
	"os"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
)

const (
	requiredEnvironment = "gamma"
	requiredTarget      = "gamma-local"
)

type response struct {
	OwnerID     string `json:"ownerId"`
	PersonaID   string `json:"personaId"`
	AccessToken string `json:"accessToken"`
}

func main() {
	if strings.TrimSpace(os.Getenv("APP_ENV")) != requiredEnvironment ||
		strings.TrimSpace(os.Getenv("QWQ_LOCAL_ACCEPTANCE_TARGET")) != requiredTarget {
		log.Fatal("acceptance session issuer is restricted to local Gamma")
	}
	ownerID := requiredEnv("QWQ_ACCEPTANCE_OWNER_ID")
	personaID := requiredEnv("QWQ_ACCEPTANCE_PERSONA_ID")
	config, err := rtauth.LoadAccessTokenConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		log.Fatal("load access token config")
	}
	signer, err := rtauth.NewHS256Signer(config)
	if err != nil {
		log.Fatal("create access token signer")
	}
	token, err := signer.Sign(rtauth.TokenSubject{AccountID: ownerID, PersonaID: personaID})
	if err != nil {
		log.Fatal("issue access token")
	}
	if err := json.NewEncoder(os.Stdout).Encode(response{
		OwnerID: ownerID, PersonaID: personaID, AccessToken: token,
	}); err != nil {
		log.Fatal("encode acceptance session")
	}
}

func requiredEnv(name string) string {
	value := strings.TrimSpace(os.Getenv(name))
	if value == "" {
		log.Fatalf("required environment is missing: %s", name)
	}
	return value
}
