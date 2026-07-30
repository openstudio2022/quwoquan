// spec_ref: specs/feature-tree/user-identity-profile-relationship/spec.md#dom-001
package local_contract

import (
	"fmt"
	"strings"
	"testing"

	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	useridentity "quwoquan_service/services/user-service/internal/account/user_account/domain/user/identity"
)

const (
	testIdentityEntropy      = "01j00000000000000000000000"
	testOtherIdentityEntropy = "01j00000000000000000000001"
)

func TestUserIdentityUsesOneCanonicalAccountAndPersonaShape(t *testing.T) {
	ownerID, err := useridentity.NewOwnerID("ph", testIdentityEntropy)
	if err != nil {
		t.Fatal(err)
	}
	parsedOwnerID, err := useridentity.ParseOwnerID(ownerID.String())
	if err != nil {
		t.Fatalf("parse generated owner identity: %v", err)
	}
	ownerParts := strings.Split(ownerID.String(), "_")
	if len(ownerParts) != 5 || ownerParts[0] != "uo" || ownerParts[1] != "01" ||
		ownerParts[2] != "ph" || ownerParts[3] != ownerID.LogicalShardHex() ||
		ownerParts[4] != testIdentityEntropy {
		t.Fatalf("unexpected canonical owner identity: %q", ownerID.String())
	}
	if parsedOwnerID.RoutingKey() != ownerID.RoutingKey() {
		t.Fatalf("owner routing changed after parse: %q", ownerID.String())
	}

	personaID, err := useridentity.NewPersonaID(
		ownerID.LogicalShardHex(),
		testOtherIdentityEntropy,
	)
	if err != nil {
		t.Fatal(err)
	}
	parsedPersonaID, err := useridentity.ParsePersonaID(personaID.String())
	if err != nil {
		t.Fatalf("parse generated persona identity: %v", err)
	}
	personaParts := strings.Split(personaID.String(), "_")
	if len(personaParts) != 4 || personaParts[0] != "us" ||
		personaParts[1] != "01" ||
		parsedPersonaID.LogicalShardHex() != ownerID.LogicalShardHex() ||
		personaParts[3] != testOtherIdentityEntropy {
		t.Fatalf("unexpected canonical persona identity: %q", personaID.String())
	}

	for _, fixture := range []struct {
		origin   string
		entropy  string
		expected string
	}{
		{
			origin: "ph", entropy: testIdentityEntropy,
			expected: "uo_01_ph_333a_01j00000000000000000000000",
		},
		{
			origin: "ph", entropy: testOtherIdentityEntropy,
			expected: "uo_01_ph_2cdb_01j00000000000000000000001",
		},
		{
			origin: "ad", entropy: "00000000000000000000000000",
			expected: "uo_01_ad_30a1_00000000000000000000000000",
		},
		{
			origin: "ad", entropy: "01j00000000000000000000002",
			expected: "uo_01_ad_3338_01j00000000000000000000002",
		},
	} {
		fixtureID, fixtureErr := useridentity.NewOwnerID(fixture.origin, fixture.entropy)
		if fixtureErr != nil {
			t.Fatal(fixtureErr)
		}
		if fixtureID.String() != fixture.expected {
			t.Fatalf("canonical hash fixture changed: got=%q want=%q", fixtureID.String(), fixture.expected)
		}
	}
}

func TestUserIdentityRejectsMissingCanonicalMarkerAliasesAndRoutingMismatch(t *testing.T) {
	ownerID, err := useridentity.NewOwnerID("ph", testIdentityEntropy)
	if err != nil {
		t.Fatal(err)
	}
	personaID, err := useridentity.NewPersonaID(
		ownerID.LogicalShardHex(),
		testOtherIdentityEntropy,
	)
	if err != nil {
		t.Fatal(err)
	}

	missingMarkerOwnerShape := strings.Replace(ownerID.String(), "uo_01_", "uo_", 1)
	wrongShard := fmt.Sprintf("uo_01_ph_%04x_%s", (ownerID.LogicalShard()+1)%useridentity.SlotCount, testIdentityEntropy)
	for _, raw := range []string{
		missingMarkerOwnerShape,
		wrongShard,
		strings.ToUpper(ownerID.String()),
		" " + ownerID.String(),
		strings.Replace(ownerID.String(), "uo_", "owner_", 1),
	} {
		if useridentity.IsCanonicalOwnerID(raw) {
			t.Fatalf("noncanonical owner identity was accepted: %q", raw)
		}
	}

	missingMarkerPersonaShape := strings.Replace(personaID.String(), "us_01_", "us_", 1)
	for _, raw := range []string{
		missingMarkerPersonaShape,
		strings.ToUpper(personaID.String()),
		personaID.String() + "_alias",
	} {
		if useridentity.IsCanonicalPersonaID(raw) {
			t.Fatalf("noncanonical persona identity was accepted: %q", raw)
		}
	}
}

func TestShardDirectoryFailsClosedForNoncanonicalOwnerIdentity(t *testing.T) {
	ownerID, err := useridentity.NewOwnerID("ph", testIdentityEntropy)
	if err != nil {
		t.Fatal(err)
	}
	directory := &application.ShardDirectory{
		SlotCount:            useridentity.SlotCount,
		HashFn:               useridentity.HashFunction,
		DefaultPhysicalShard: "user-primary-a",
		Entries: []application.ShardDirectoryEntry{
			{Prefix: "", PhysicalShard: "user-primary-a"},
			{Prefix: ownerID.RoutingKey()[:5], PhysicalShard: "user-primary-b"},
		},
	}
	if err := directory.Validate(); err != nil {
		t.Fatal(err)
	}
	physicalShard, err := directory.ResolvePhysicalShardForOwnerID(ownerID.String())
	if err != nil || physicalShard != "user-primary-b" {
		t.Fatalf("canonical owner routing: shard=%q err=%v", physicalShard, err)
	}

	missingMarkerOwnerShape := strings.Replace(ownerID.String(), "uo_01_", "uo_", 1)
	if _, err := directory.ResolvePhysicalShardForOwnerID(missingMarkerOwnerShape); err == nil {
		t.Fatal("identity without the frozen format marker fell back to the default shard")
	}
}
