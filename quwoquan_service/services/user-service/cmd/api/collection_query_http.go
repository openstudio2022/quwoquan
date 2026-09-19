package bootstrap

import (
	"net/http"
	inbound "quwoquan_service/services/user-service/internal/account/user_account/adapters/inbound/http"
	authority "quwoquan_service/services/user-service/internal/account/user_account/application"
	ports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
	"time"
)

// CollectionQuerySecuritySnapshot 是公开组合入口使用的最小账号读型，不扩展现有 authority。
type CollectionQuerySecuritySnapshot = ports.AccountSecuritySnapshot

// NewCollectionQueryAuthorityHTTP 是独立模块组合入口；生产与真实跨服务 conformance 使用同一构造链。
func NewCollectionQueryAuthorityHTTP(source authority.SourceCredentialVerifier, accounts ports.AccountSecurityReader, personas authority.PersonaOwnershipReader, keyID string, keys map[string][]byte, now func() time.Time) (http.Handler, error) {
	a, err := authority.NewCollectionQueryAuthority(source, accounts, personas, authority.CollectionAuthorityKeys{ActiveID: keyID, VerificationKeys: keys}, now)
	if err != nil {
		return nil, err
	}
	mux := http.NewServeMux()
	inbound.NewCollectionQueryAuthorityHandler(a).RegisterRoutes(mux)
	return mux, nil
}
