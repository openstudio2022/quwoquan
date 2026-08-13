// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
package local_contract

import (
	"testing"

	credentialmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
)

const (
	managedAcceptancePhone   = "+8619910000000"
	managedAcceptanceOwnerID = "uo_01_ph_333a_01j00000000000000000000000"
)

func TestManagedAcceptancePhoneUsesExactCanonicalOwnerIdentity(t *testing.T) {
	binding := application.ManagedAcceptanceBinding{
		Phone:   managedAcceptancePhone,
		OwnerID: managedAcceptanceOwnerID,
	}
	identity, err := binding.ResolveOwnerIdentity(
		credentialmodel.CredentialType("phone"),
		managedAcceptancePhone,
		"phone",
		"ph",
	)
	if err != nil {
		t.Fatal(err)
	}
	if identity.OwnerID != managedAcceptanceOwnerID || identity.RootPrefix != "333a" {
		t.Fatalf("managed acceptance owner identity drifted: %+v", identity)
	}

	other, err := binding.ResolveOwnerIdentity(
		credentialmodel.CredentialType("phone"),
		"+8619910000001",
		"phone",
		"ph",
	)
	if err != nil {
		t.Fatal(err)
	}
	if other.OwnerID == managedAcceptanceOwnerID {
		t.Fatal("unrelated phone reused the managed acceptance identity")
	}
}

func TestManagedAcceptanceIdentityRejectsOriginMismatch(t *testing.T) {
	binding := application.ManagedAcceptanceBinding{
		Phone:   managedAcceptancePhone,
		OwnerID: managedAcceptanceOwnerID,
	}
	if _, err := binding.ResolveOwnerIdentity(
		credentialmodel.CredentialType("phone"),
		managedAcceptancePhone,
		"federated",
		"f1",
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
		binding := application.ManagedAcceptanceBinding{
			Phone:   managedAcceptancePhone,
			OwnerID: ownerID,
		}
		identity, err := binding.ResolveOwnerIdentity(
			credentialmodel.CredentialType("phone"),
			managedAcceptancePhone,
			"phone",
			"ph",
		)
		if err != nil || identity.OwnerID != ownerID {
			t.Fatalf("%s owner identity is not canonical: %q (%v)", target, ownerID, err)
		}
	}
}
