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

// resolveResearchAccountAllowlist 复用 research identity 授权解析取账号闭集
// （DEC-032）：授权未启用时返回空闭集且无错误，登录签发不附加 research role；
// 启用但配置不闭合时 fail closed，与 session/attestation 组合的失败面一致。
func resolveResearchAccountAllowlist(
	appEnv string,
	cfg config,
) ([]string, error) {
	authority, err := researchapp.ResolveResearchIdentityAuthority(
		appEnv,
		cfg.ResearchIdentity.Enabled,
		cfg.ResearchIdentity.TTLSeconds,
	)
	if err != nil {
		return nil, err
	}
	if !authority.Enabled {
		return nil, nil
	}
	return authority.AccountIDs, nil
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
