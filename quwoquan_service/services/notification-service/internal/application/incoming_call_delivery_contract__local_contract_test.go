package application

import (
	"crypto/sha256"
	"encoding/hex"
	"testing"
	"time"

	notification "quwoquan_service/services/notification-service/internal/domain/notification"
)

func TestIncomingCallContractRequiresCanonicalDeliveryIdentity(t *testing.T) {
	t.Parallel()
	callID := "754b4604-a450-4ceb-b18d-d604d2a8f746"
	personaID := "persona-contract"
	sum := sha256.Sum256([]byte(callID + "\x00" + personaID))
	event := notification.IncomingCallRingingEvent{
		EventID:         "event-contract",
		CallID:          callID,
		TargetPersonaID: personaID,
		CallType:        "audio",
		CallerName:      "caller",
		CallerAvatarURL: "",
		SourceLabel:     "direct_call",
		TrustRelation:   "known",
		ExpiresAt:       time.Now().UTC().Add(30 * time.Second),
		DeliveryKey:     "sha256:" + hex.EncodeToString(sum[:]),
	}
	if err := validateIncomingCallRingingEvent(event); err != nil {
		t.Fatalf("canonical event rejected: %v", err)
	}
	event.DeliveryKey = "sha256:forged"
	if err := validateIncomingCallRingingEvent(event); err == nil {
		t.Fatal("forged deliveryKey must be rejected")
	}
}
