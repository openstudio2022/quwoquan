// Command acceptance-session issues an ephemeral bearer for a seeded local
// integration acceptance principal. It is an Ops-only process boundary, not an
// HTTP login route or a production authentication bypass.
package main

import (
	"encoding/json"
	"log"
	"os"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	accountsession "quwoquan_service/services/user-service/internal/account/account_session/application"
)

type response struct {
	OwnerID     string `json:"ownerId"`
	PersonaID   string `json:"personaId"`
	AccessToken string `json:"accessToken"`
}

func main() {
	environment := strings.TrimSpace(os.Getenv("APP_ENV"))
	target := strings.TrimSpace(os.Getenv("QWQ_LOCAL_ACCEPTANCE_TARGET"))
	if accountsession.LocalAcceptanceTargets[environment] != target {
		log.Fatal("acceptance session issuer is restricted to declared local integration targets")
	}
	ownerID := requiredEnv("QWQ_ACCEPTANCE_OWNER_ID")
	personaID := requiredEnv("QWQ_ACCEPTANCE_PERSONA_ID")
	subject, err := accountsession.Subject(
		strings.TrimSpace(os.Getenv("QWQ_ACCEPTANCE_PROFILE")),
		ownerID,
		personaID,
	)
	if err != nil {
		log.Fatal(err)
	}
	config, err := rtauth.LoadAccessTokenConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		log.Fatal("load access token config")
	}
	signer, err := rtauth.NewHS256Signer(config)
	if err != nil {
		log.Fatal("create access token signer")
	}
	token, err := signer.Sign(subject)
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
