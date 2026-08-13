package account_session

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strings"
	"time"

	useridentity "quwoquan_service/services/user-service/internal/account/user_account/domain/user/identity"
)

// Research identity 运行时授权的唯一 env 契约；cmd 组合层与验收装配共用。
const (
	ResearchIdentityKeyEnv       = "USER_RESEARCH_IDENTITY_ATTESTATION_KEY_BASE64"
	ResearchIdentityAllowlistEnv = "USER_RESEARCH_IDENTITY_ACCOUNT_ID_ALLOWLIST_JSON"
	ManagedAcceptanceIdentityEnv = "USER_MANAGED_ACCEPTANCE_IDENTITY_JSON"
)

// ManagedAcceptanceIdentity 是 target-scoped 受管验收身份的运行时绑定：
// 一个手机号凭据、一个 canonical owner 账号与其 subject hash 必须同时成立。
type ManagedAcceptanceIdentity struct {
	Phone       string `json:"phone"`
	AccountID   string `json:"accountId"`
	SubjectHash string `json:"subjectHash"`
}

// LoadManagedAcceptanceIdentity 解析并校验受管验收身份绑定；任何字段缺失、
// 非 canonical 账号或 subject hash 漂移都必须 fail closed。
func LoadManagedAcceptanceIdentity() (ManagedAcceptanceIdentity, error) {
	var identity ManagedAcceptanceIdentity
	if err := json.Unmarshal(
		[]byte(strings.TrimSpace(os.Getenv(ManagedAcceptanceIdentityEnv))),
		&identity,
	); err != nil {
		return ManagedAcceptanceIdentity{}, errors.New(
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
		return ManagedAcceptanceIdentity{}, errors.New(
			"managed acceptance identity is missing or invalid",
		)
	}
	return identity, nil
}

// ResearchIdentityAuthority 是 research session 组合的已解析运行时授权；
// Enabled=false 表示组合层必须装配 unavailable facade。
type ResearchIdentityAuthority struct {
	Enabled    bool
	AccountIDs []string
	Key        []byte
	TTL        time.Duration
}

// ResolveResearchIdentityAuthority 汇聚 research identity 授权的全部启用决策：
// 生产环境拒绝启用，attestation key、allowlist 与受管验收身份三者必须闭合，
// 否则 fail closed；disabled 时返回零值授权且无错误。
func ResolveResearchIdentityAuthority(
	appEnv string,
	enabled bool,
	ttlSeconds int,
) (ResearchIdentityAuthority, error) {
	if !enabled {
		return ResearchIdentityAuthority{}, nil
	}
	if appEnv != "alpha" && appEnv != "beta" && appEnv != "gamma" {
		return ResearchIdentityAuthority{}, fmt.Errorf(
			"research identity authority may only be enabled in nonproduction, got %q",
			appEnv,
		)
	}
	key, err := base64.StdEncoding.DecodeString(
		strings.TrimSpace(os.Getenv(ResearchIdentityKeyEnv)),
	)
	if err != nil || len(key) < 32 {
		return ResearchIdentityAuthority{}, errors.New(
			"research identity attestation key is missing or invalid",
		)
	}
	var accountIDs []string
	if err := json.Unmarshal(
		[]byte(strings.TrimSpace(os.Getenv(ResearchIdentityAllowlistEnv))),
		&accountIDs,
	); err != nil {
		return ResearchIdentityAuthority{}, errors.New(
			"research identity account allowlist is missing or invalid",
		)
	}
	managedIdentity, err := LoadManagedAcceptanceIdentity()
	if err != nil || len(accountIDs) != 1 ||
		strings.TrimSpace(accountIDs[0]) != managedIdentity.AccountID {
		return ResearchIdentityAuthority{}, errors.New(
			"research identity allowlist does not match the managed acceptance identity",
		)
	}
	return ResearchIdentityAuthority{
		Enabled:    true,
		AccountIDs: accountIDs,
		Key:        key,
		TTL:        time.Duration(ttlSeconds) * time.Second,
	}, nil
}
