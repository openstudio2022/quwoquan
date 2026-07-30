package application

import (
	"fmt"
	"strings"

	runtimeid "quwoquan_service/runtime/id"
	credentialmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	useridentity "quwoquan_service/services/user-service/internal/account/user_account/domain/user/identity"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

const (
	identityEntropyPrefix runtimeid.Prefix = "uid_"

	originCodeAnonymousDevice = "ad"
	originCodePhone           = "ph"
	originCodeFederatedSlotA  = "f1"
	originCodeFederatedSlotB  = "f2"
	originCodeFederatedSlotC  = "f3"
	originCodeMigratedSeed    = "mg"

	identityOriginAnonymousDevice = "anonymous_device"
	identityOriginPhone           = "phone"
	identityOriginFederated       = "federated"
	identityOriginMigratedSeed    = "migrated_seed"

	accountStateAnonymous = "anonymous"
	accountStateActive    = "active"

	retentionPolicyPreserve = "preserve"
)

type identityDescriptor struct {
	OwnerID      string
	RootPrefix   string
	LogicalShard int
}

func init() {
	_ = runtimeid.DefaultRegistry.Register(identityEntropyPrefix, "UserIdentityEntropy")
}

func buildOwnerIdentity(credType string) (identityDescriptor, error) {
	identityOrigin, originCode := identityOriginForCredentialType(credType)
	return buildOwnerIdentityForOrigin(identityOrigin, originCode)
}

func buildOwnerIdentityForOrigin(
	identityOrigin string,
	originCode string,
) (identityDescriptor, error) {
	if strings.TrimSpace(identityOrigin) == "" || strings.TrimSpace(originCode) == "" {
		return identityDescriptor{}, fmt.Errorf("identity origin is required")
	}
	entropyBody, err := generateIdentityEntropyBody()
	if err != nil {
		return identityDescriptor{}, err
	}
	ownerID, err := useridentity.NewOwnerID(originCode, entropyBody)
	if err != nil {
		return identityDescriptor{}, fmt.Errorf("build owner identity: %w", err)
	}
	return identityDescriptor{
		OwnerID:      ownerID.String(),
		RootPrefix:   ownerID.LogicalShardHex(),
		LogicalShard: ownerID.LogicalShard(),
	}, nil
}

func buildPersonaIdentity(rootPrefix string) (string, error) {
	entropyBody, err := generateIdentityEntropyBody()
	if err != nil {
		return "", err
	}
	personaID, err := useridentity.NewPersonaID(rootPrefix, entropyBody)
	if err != nil {
		return "", fmt.Errorf("build persona identity: %w", err)
	}
	return personaID.String(), nil
}

func generateIdentityEntropyBody() (string, error) {
	raw, err := runtimeid.Generate(identityEntropyPrefix)
	if err != nil {
		return "", fmt.Errorf("generate identity entropy: %w", err)
	}
	return strings.ToLower(strings.TrimPrefix(raw, string(identityEntropyPrefix))), nil
}
func extractOwnerRootPrefix(ownerID string) (string, error) {
	parsed, err := useridentity.ParseOwnerID(ownerID)
	if err != nil {
		return "", fmt.Errorf("parse owner identity: %w", err)
	}
	return parsed.LogicalShardHex(), nil
}

func identityOriginForCredentialType(credType string) (identityOrigin string, originCode string) {
	switch strings.TrimSpace(credType) {
	case credentialAnonymousDevice:
		return identityOriginAnonymousDevice, originCodeAnonymousDevice
	case credentialPhone, credentialCarrierPhone:
		return identityOriginPhone, originCodePhone
	case string(credentialmodel.CredentialTypeFederatedSlotA):
		return identityOriginFederated, originCodeFederatedSlotA
	case string(credentialmodel.CredentialTypeFederatedSlotB):
		return identityOriginFederated, originCodeFederatedSlotB
	case string(credentialmodel.CredentialTypeFederatedSlotC):
		return identityOriginFederated, originCodeFederatedSlotC
	default:
		return "", ""
	}
}

func anonymousRetentionPolicyForCredentialType(credType string) string {
	return retentionPolicyPreserve
}

func accountStateForCredentialType(credType string) string {
	if strings.TrimSpace(credType) == credentialAnonymousDevice {
		return accountStateAnonymous
	}
	return accountStateActive
}

func normalizeAnonymousCredentialKey(deviceFingerprintHash string) string {
	return strings.ToLower(strings.TrimSpace(deviceFingerprintHash))
}

func promoteRegisteredProfile(profile *model.UserProfile) {
	if profile == nil {
		return
	}
	if strings.TrimSpace(profile.AccountState) == accountStateAnonymous {
		profile.AccountState = accountStateActive
		profile.AnonymousRetentionPolicy = retentionPolicyPreserve
	}
}
