package local_contract

import (
	"testing"
	"time"

	connectionmodel "quwoquan_service/services/realtime-gateway/internal/realtime/connection/domain/model"
)

func TestConnectionSessionCannotBeRevivedAfterTTL(t *testing.T) {
	t.Parallel()
	startedAt := time.Date(2026, 8, 2, 8, 0, 0, 0, time.UTC)
	session, err := connectionmodel.StartSession(
		"connection-domain",
		connectionmodel.Identity{
			AccountID: "account-domain",
			PersonaID: "persona-domain",
			DeviceID:  "device-domain",
		},
		7,
		"websocket",
		11,
		startedAt,
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := session.Renew(startedAt.Add(20 * time.Second)); err != nil {
		t.Fatalf("authenticated heartbeat must renew live session: %v", err)
	}
	expiresAt := session.ExpiresAt
	if err := session.Renew(expiresAt); err == nil {
		t.Fatal("heartbeat at expiry must not revive runtime session")
	}
	if !session.ExpiresAt.Equal(expiresAt) {
		t.Fatalf("expired session changed expiry: got %s want %s", session.ExpiresAt, expiresAt)
	}
}
