// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/realtime-gateway/realtime-channel-delivery/spec.md#gwt-002
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/domain/model"
	presenceredis "quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/infrastructure/redisstore"
)

func TestPresenceProjectionUsesFenceAndCleansOnlyStaleDevice(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	store, err := presenceredis.NewStore(client)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 7, 20, 15, 0, 0, 0, time.UTC)
	active, err := model.NewDevice(
		"account-presence",
		"persona-presence",
		"device-active",
		"conn-new",
		"node-a",
		"websocket",
		now.Add(-10*time.Second),
		2,
	)
	if err != nil {
		t.Fatal(err)
	}
	stale, err := model.NewDevice(
		"account-presence",
		"persona-presence",
		"device-stale",
		"conn-stale",
		"node-b",
		"websocket",
		now.Add(-61*time.Second),
		1,
	)
	if err != nil {
		t.Fatal(err)
	}
	for _, candidate := range []model.Device{active, stale} {
		if written, writeErr := store.UpsertIfNewer(ctx, candidate); writeErr != nil || !written {
			t.Fatalf("write %+v: written=%v err=%v", candidate, written, writeErr)
		}
	}
	older, err := model.NewDevice(
		active.AccountID,
		active.PersonaID,
		active.DeviceID,
		"conn-old",
		"node-old",
		active.Transport,
		now,
		1,
	)
	if err != nil {
		t.Fatal(err)
	}
	if written, writeErr := store.UpsertIfNewer(ctx, older); writeErr != nil || written {
		t.Fatalf("old fence must be rejected: written=%v err=%v", written, writeErr)
	}
	view, err := store.ReadPresence(ctx, active.PersonaID, now)
	if err != nil {
		t.Fatalf("read presence: %v", err)
	}
	if len(view.Devices) != 1 ||
		view.Devices[0].DeviceID != active.DeviceID ||
		view.Devices[0].ConnectionID != active.ConnectionID ||
		view.Devices[0].Sequence != active.Sequence {
		t.Fatalf("presence view=%+v", view)
	}
	if _, err := client.HGet(
		ctx,
		"presence:persona:"+active.PersonaID,
		stale.DeviceID,
	); !errors.Is(err, rtredis.ErrKeyNotFound) {
		t.Fatalf("stale field must be removed, err=%v", err)
	}
	if _, err := client.HGet(
		ctx,
		"presence:persona:"+active.PersonaID,
		active.DeviceID,
	); err != nil {
		t.Fatalf("active field must remain despite stale sibling: %v", err)
	}
}
