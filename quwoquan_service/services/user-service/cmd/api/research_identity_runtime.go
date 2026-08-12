package main

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	researchhttp "quwoquan_service/services/user-service/internal/account/account_session/adapters/inbound/http"
	researchapp "quwoquan_service/services/user-service/internal/account/account_session/application"
	researchmessaging "quwoquan_service/services/user-service/internal/account/account_session/infrastructure/messaging"
	useridentity "quwoquan_service/services/user-service/internal/account/user_account/domain/user/identity"
)

const (
	researchIdentityKeyEnv       = "USER_RESEARCH_IDENTITY_ATTESTATION_KEY_BASE64"
	researchIdentityAllowlistEnv = "USER_RESEARCH_IDENTITY_ACCOUNT_ID_ALLOWLIST_JSON"
	managedAcceptanceIdentityEnv = "USER_MANAGED_ACCEPTANCE_IDENTITY_JSON"
)

type managedAcceptanceIdentity struct {
	Phone       string `json:"phone"`
	AccountID   string `json:"accountId"`
	SubjectHash string `json:"subjectHash"`
}

func loadManagedAcceptanceIdentity() (managedAcceptanceIdentity, error) {
	var identity managedAcceptanceIdentity
	if err := json.Unmarshal(
		[]byte(strings.TrimSpace(os.Getenv(managedAcceptanceIdentityEnv))),
		&identity,
	); err != nil {
		return managedAcceptanceIdentity{}, errors.New(
			"managed acceptance identity is missing or invalid",
		)
	}
	identity.Phone = strings.TrimSpace(identity.Phone)
	identity.AccountID = strings.TrimSpace(identity.AccountID)
	identity.SubjectHash = strings.TrimSpace(identity.SubjectHash)
	expectedSubjectHash := fmt.Sprintf(
		"sha256:%x",
		sha256.Sum256([]byte(identity.Phone)),
	)
	if identity.Phone == "" || identity.Phone[0] != '+' ||
		!useridentity.IsCanonicalOwnerID(identity.AccountID) ||
		identity.SubjectHash != expectedSubjectHash {
		return managedAcceptanceIdentity{}, errors.New(
			"managed acceptance identity is missing or invalid",
		)
	}
	return identity, nil
}

func buildResearchSessionHandler(
	appEnv string,
	cfg config,
	transport runtimemessaging.DurableRecordAppender,
) (*researchhttp.ResearchSessionHandler, error) {
	if !cfg.ResearchIdentity.Enabled {
		return researchhttp.NewResearchSessionHandler(
			researchapp.NewUnavailableResearchSessionCommandFacade(),
		)
	}
	if appEnv != "alpha" && appEnv != "beta" && appEnv != "gamma" {
		return nil, fmt.Errorf(
			"research identity authority may only be enabled in nonproduction, got %q",
			appEnv,
		)
	}
	key, err := base64.StdEncoding.DecodeString(
		strings.TrimSpace(os.Getenv(researchIdentityKeyEnv)),
	)
	if err != nil || len(key) < 32 {
		return nil, errors.New("research identity attestation key is missing or invalid")
	}
	var accountIDs []string
	if err := json.Unmarshal(
		[]byte(strings.TrimSpace(os.Getenv(researchIdentityAllowlistEnv))),
		&accountIDs,
	); err != nil {
		return nil, errors.New("research identity account allowlist is missing or invalid")
	}
	managedIdentity, err := loadManagedAcceptanceIdentity()
	if err != nil || len(accountIDs) != 1 ||
		strings.TrimSpace(accountIDs[0]) != managedIdentity.AccountID {
		return nil, errors.New(
			"research identity allowlist does not match the managed acceptance identity",
		)
	}
	publisher, err := researchmessaging.NewResearchSessionAuditPublisher(transport)
	if err != nil {
		return nil, fmt.Errorf("research identity audit composition: %w", err)
	}
	facade, err := researchapp.NewResearchSessionCommandFacade(
		accountIDs,
		key,
		time.Duration(cfg.ResearchIdentity.TTLSeconds)*time.Second,
		publisher,
	)
	if err != nil {
		return nil, fmt.Errorf("research identity command composition: %w", err)
	}
	return researchhttp.NewResearchSessionHandler(facade)
}
