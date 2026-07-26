package application

import (
	"fmt"
	"strings"

	xxhash "github.com/cespare/xxhash/v2"

	runtimeid "quwoquan_service/runtime/id"
	credentialmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

const (
	identityRuleVersion                    = "01"
	identitySlotCount                      = 16384
	identityHashFunction                   = "xxhash64"
	ownerIDFormat                          = "uo_%s_%s_%s_%s"
	subAccountIDFormat                     = "us_%s_%s_%s"
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
	logicalShard := computeLogicalShard(originCode, entropyBody)
	rootPrefix := fmt.Sprintf("%04x", logicalShard)
	return identityDescriptor{
		OwnerID:      fmt.Sprintf(ownerIDFormat, identityRuleVersion, originCode, rootPrefix, entropyBody),
		RootPrefix:   rootPrefix,
		LogicalShard: logicalShard,
	}, nil
}

func buildSubAccountIdentity(rootPrefix string) (string, error) {
	entropyBody, err := generateIdentityEntropyBody()
	if err != nil {
		return "", err
	}
	return fmt.Sprintf(subAccountIDFormat, identityRuleVersion, strings.TrimSpace(rootPrefix), entropyBody), nil
}

func generateIdentityEntropyBody() (string, error) {
	raw, err := runtimeid.Generate(identityEntropyPrefix)
	if err != nil {
		return "", fmt.Errorf("generate identity entropy: %w", err)
	}
	return strings.ToLower(strings.TrimPrefix(raw, string(identityEntropyPrefix))), nil
}

func computeLogicalShard(originCode, entropyBody string) int {
	return int(computeRoutingHash(originCode, entropyBody) % identitySlotCount)
}

func computeRoutingHash(originCode, entropyBody string) uint64 {
	seed := identityRuleVersion + "|" + strings.TrimSpace(originCode) + "|" + strings.TrimSpace(entropyBody)
	return xxhash.Sum64String(seed)
}

func buildShardRoutingKey(originCode, entropyBody string) string {
	routingHash := computeRoutingHash(originCode, entropyBody)
	logicalShard := int(routingHash % identitySlotCount)
	return fmt.Sprintf("%04x%016x", logicalShard, routingHash)
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
