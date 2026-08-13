package application

import (
	"errors"
	"strings"

	credentialmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	useridentity "quwoquan_service/services/user-service/internal/account/user_account/domain/user/identity"
)

// ManagedAcceptanceBinding 把唯一的 target-scoped 受管验收手机号钉到一个
// canonical owner 账号；零值绑定表示未启用，所有凭据都走全新身份。
type ManagedAcceptanceBinding struct {
	Phone   string
	OwnerID string
}

// ResolveOwnerIdentity 在凭据命中受管验收绑定时复用钉住的 canonical owner
// 身份，其余凭据一律生成全新 origin 身份；绑定账号与凭据 origin 不一致时
// 必须 fail closed，禁止跨 origin 复用验收账号。
func (b ManagedAcceptanceBinding) ResolveOwnerIdentity(
	credentialType credentialmodel.CredentialType,
	credentialKey string,
	identityOrigin string,
	originCode string,
) (OwnerIdentityDescriptor, error) {
	if credentialType != credentialmodel.CredentialType(credentialPhone) ||
		strings.TrimSpace(credentialKey) != b.Phone ||
		b.OwnerID == "" {
		return buildOwnerIdentityForOrigin(identityOrigin, originCode)
	}
	parsed, err := useridentity.ParseOwnerID(b.OwnerID)
	if err != nil || parsed.OriginCode() != originCode {
		return OwnerIdentityDescriptor{}, errors.New(
			"managed acceptance identity is not canonical for the credential origin",
		)
	}
	return OwnerIdentityDescriptor{
		OwnerID:      parsed.String(),
		RootPrefix:   parsed.LogicalShardHex(),
		LogicalShard: parsed.LogicalShard(),
	}, nil
}
