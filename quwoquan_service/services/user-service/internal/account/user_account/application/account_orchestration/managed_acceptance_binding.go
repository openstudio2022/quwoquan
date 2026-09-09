package application

import (
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"os"
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

// LoadManagedAcceptanceBinding 只消费显式环境注入的普通验收账号绑定；
// 缺席表示不启用，存在但错绑时拒绝，不签发任何专属角色或证明。
func LoadManagedAcceptanceBinding() (ManagedAcceptanceBinding, error) {
	raw := strings.TrimSpace(os.Getenv("USER_MANAGED_ACCEPTANCE_IDENTITY_JSON"))
	if raw == "" {
		return ManagedAcceptanceBinding{}, nil
	}
	var identity struct {
		Phone string `json:"phone"`
		AccountID string `json:"accountId"`
		SubjectHash string `json:"subjectHash"`
	}
	decoder := json.NewDecoder(strings.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&identity); err != nil {
		return ManagedAcceptanceBinding{}, errors.New("managed acceptance identity is invalid")
	}
	if identity.Phone == "" || identity.Phone != strings.TrimSpace(identity.Phone) ||
		!strings.HasPrefix(identity.Phone, "+") || !useridentity.IsCanonicalOwnerID(identity.AccountID) ||
		identity.SubjectHash != fmt.Sprintf("sha256:%x", sha256.Sum256([]byte(identity.Phone))) {
		return ManagedAcceptanceBinding{}, errors.New("managed acceptance identity binding is invalid")
	}
	return ManagedAcceptanceBinding{Phone: identity.Phone, OwnerID: identity.AccountID}, nil
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
