package bootstrap

import (
	"fmt"

	runtimemessaging "quwoquan_service/runtime/messaging"
	researchhttp "quwoquan_service/services/user-service/internal/account/account_session/adapters/inbound/http"
	researchapp "quwoquan_service/services/user-service/internal/account/account_session/application"
	researchmessaging "quwoquan_service/services/user-service/internal/account/account_session/infrastructure/messaging"
)

func loadManagedAcceptanceIdentity() (researchapp.ManagedAcceptanceIdentity, error) {
	return researchapp.LoadManagedAcceptanceIdentity()
}

func buildResearchSessionHandler(
	appEnv string,
	cfg config,
	transport runtimemessaging.DurableRecordAppender,
) (*researchhttp.ResearchSessionHandler, error) {
	authority, err := researchapp.ResolveResearchIdentityAuthority(
		appEnv,
		cfg.ResearchIdentity.Enabled,
		cfg.ResearchIdentity.TTLSeconds,
	)
	if err != nil {
		return nil, err
	}
	if !authority.Enabled {
		return researchhttp.NewResearchSessionHandler(
			researchapp.NewUnavailableResearchSessionCommandFacade(),
		)
	}
	publisher, err := researchmessaging.NewResearchSessionAuditPublisher(transport)
	if err != nil {
		return nil, fmt.Errorf("research identity audit composition: %w", err)
	}
	facade, err := researchapp.NewResearchSessionCommandFacade(
		authority.AccountIDs,
		authority.Key,
		authority.TTL,
		publisher,
	)
	if err != nil {
		return nil, fmt.Errorf("research identity command composition: %w", err)
	}
	return researchhttp.NewResearchSessionHandler(facade)
}

func buildResearchSessionAttestationHandler(
	appEnv string,
	cfg config,
) (*researchhttp.ResearchSessionAttestationHandler, error) {
	authority, err := researchapp.ResolveResearchIdentityAuthority(
		appEnv,
		cfg.ResearchIdentity.Enabled,
		cfg.ResearchIdentity.TTLSeconds,
	)
	if err != nil {
		return nil, err
	}
	if !authority.Enabled {
		return researchhttp.NewResearchSessionAttestationHandler(
			researchapp.NewUnavailableResearchSessionQueryFacade(),
		)
	}
	facade, err := researchapp.NewResearchSessionQueryFacade(authority.Key)
	if err != nil {
		return nil, fmt.Errorf("research identity query composition: %w", err)
	}
	return researchhttp.NewResearchSessionAttestationHandler(facade)
}
