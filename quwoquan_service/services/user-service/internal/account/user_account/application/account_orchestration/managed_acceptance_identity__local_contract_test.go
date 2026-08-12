package application

import (
	"testing"

	credentialmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
)

func TestManagedAcceptancePhoneUsesExactCanonicalOwnerIdentity(t *testing.T) {
	const phone = "+8619910000000"
	const ownerID = "uo_01_ph_333a_01j00000000000000000000000"
	service := NewAuthService(
		nil,
		nil,
		nil,
		nil,
		nil,
		WithManagedAcceptanceIdentity(phone, ownerID),
	)
	identity, err := service.newOwnerIdentity(
		credentialmodel.CredentialType("phone"),
		phone,
		identityOriginPhone,
		originCodePhone,
	)
	if err != nil {
		t.Fatal(err)
	}
	if identity.OwnerID != ownerID || identity.RootPrefix != "333a" {
		t.Fatalf("managed acceptance owner identity drifted: %+v", identity)
	}

	other, err := service.newOwnerIdentity(
		credentialmodel.CredentialType("phone"),
		"+8619910000001",
		identityOriginPhone,
		originCodePhone,
	)
	if err != nil {
		t.Fatal(err)
	}
	if other.OwnerID == ownerID {
		t.Fatal("unrelated phone reused the managed acceptance identity")
	}
}

func TestManagedAcceptanceIdentityRejectsOriginMismatch(t *testing.T) {
	service := NewAuthService(
		nil,
		nil,
		nil,
		nil,
		nil,
		WithManagedAcceptanceIdentity(
			"+8619910000000",
			"uo_01_ph_333a_01j00000000000000000000000",
		),
	)
	if _, err := service.newOwnerIdentity(
		credentialmodel.CredentialType("phone"),
		"+8619910000000",
		identityOriginFederated,
		originCodeFederatedSlotA,
	); err == nil {
		t.Fatal("managed acceptance identity accepted a credential origin mismatch")
	}
}

func TestOpsManagedAcceptanceIdentityFixturesRemainCanonical(t *testing.T) {
	fixtures := map[string]string{
		"alpha-local": "uo_01_ph_23a9_etr4y4czakhgdfhatbk2p996zp",
		"beta-local":  "uo_01_ph_047a_2y9d2bhzyce3p47qcvf5d4pzvp",
		"gamma-local": "uo_01_ph_3115_2myk50mghrz5d372577fx9h9hk",
	}
	for target, ownerID := range fixtures {
		service := NewAuthService(
			nil, nil, nil, nil, nil,
			WithManagedAcceptanceIdentity("+8619910000000", ownerID),
		)
		if service.managedAcceptanceOwnerID != ownerID {
			t.Fatalf("%s owner identity is not canonical: %q", target, ownerID)
		}
	}
}
