package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	authorityhttp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/adapters/inbound/http"
	authorityapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/application"
	authoritystore "quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/infrastructure/persistence"
	"quwoquan_service/runtime/servicekit"
)

func composeHumanAuthority(asm *servicekit.Assembly, cfg *config) (*authorityhttp.Handler, error) {
	signer, err := authorityapp.LoadEd25519Signer(cfg.HumanAuthority.SigningKeyID, cfg.HumanAuthority.SigningPrivateKeyFile, cfg.HumanAuthority.SigningPrivateKeyBase64, cfg.HumanAuthority.SigningTestKey)
	if err != nil {
		return nil, fmt.Errorf("human authority signer invalid: %w", err)
	}
	mappings, err := decodeRoleMappings(cfg.HumanAuthority.RoleMappings)
	if err != nil {
		return nil, err
	}
	roles, err := authorityapp.NewRoleMapper(mappings)
	if err != nil {
		return nil, fmt.Errorf("human authority role mappings invalid: %w", err)
	}
	githubMappings, err := decodeGitHubMappings(cfg.HumanAuthority.GitHubMappings)
	if err != nil {
		return nil, err
	}
	store, err := authoritystore.NewPostgresStore(asm.PostgresPool)
	if err != nil {
		return nil, err
	}
	if err = store.EnsureSchema(asm.Context); err != nil {
		return nil, fmt.Errorf("human authority schema initialization failed: %w", err)
	}
	facade, err := authorityapp.NewFacadeWithProvider(store, signer, githubMappings, authorityapp.ProviderIdentity{Issuer: cfg.HumanAuthority.Issuer, ProviderKind: "hosted-human-authority", ProviderVersion: cfg.HumanAuthority.ProviderVersion, ProviderCommit: cfg.HumanAuthority.ProviderCommit, ContractVersion: "human-authority-wire-v1"})
	if err != nil {
		return nil, err
	}
	return authorityhttp.NewHandler(facade, roles, []byte(cfg.HumanAuthority.GitHubWebhookSecret))
}
func decodeRoleMappings(raw string) (map[string][]string, error) {
	result := map[string][]string{}
	if err := json.Unmarshal([]byte(strings.TrimSpace(raw)), &result); err != nil {
		return nil, errors.New("human authority role mappings must be JSON object")
	}
	if len(result) == 0 {
		return nil, errors.New("human authority role mappings cannot be empty")
	}
	return result, nil
}
func decodeGitHubMappings(raw string) ([]authorityapp.GitHubMapping, error) {
	if strings.TrimSpace(raw) == "" {
		return nil, nil
	}
	var result []authorityapp.GitHubMapping
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		return nil, errors.New("human authority GitHub mappings must be JSON array")
	}
	return result, nil
}
