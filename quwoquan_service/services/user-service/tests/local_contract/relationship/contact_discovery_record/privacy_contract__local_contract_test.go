package local_contract

import (
	"encoding/json"
	"strings"
	"testing"
	"time"

	contactmodel "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/domain/model"
)

func TestContactDiscoveryRecordWireNeverExposesOwnerOrPhoneHashes(t *testing.T) {
	record := contactmodel.ContactDiscoveryRecord{
		ID: "contact-discovery-1", OwnerAccountID: "account-secret",
		HashedPhones: []string{"sha256-secret"}, MatchedPersonaIds: []string{"persona-public"},
		Status: "completed", MatchCount: 1, ExpireAt: time.Now().UTC().Add(time.Hour),
	}
	payload, err := json.Marshal(record)
	if err != nil {
		t.Fatalf("marshal contact discovery record: %v", err)
	}
	wire := string(payload)
	for _, forbidden := range []string{"account-secret", "sha256-secret", "ownerAccountId", "hashedPhones"} {
		if strings.Contains(wire, forbidden) {
			t.Fatalf("private contact discovery state leaked to wire: %s", wire)
		}
	}
	if !strings.Contains(wire, "persona-public") {
		t.Fatalf("public matched persona missing from wire: %s", wire)
	}
}
