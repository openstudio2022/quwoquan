package projection

import (
	"testing"
	"time"

	relevent "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/event"
	relmodel "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/model"
)

func TestCounterDeltas_FollowAndUnfollowAreSymmetric(t *testing.T) {
	follow := relmodel.OutboxEvent{
		EventName: relevent.PersonaFollowStateChanged,
		Payload: relmodel.OutboxPayload{
			Following:  true,
			OccurredAt: time.Now().UTC(),
		},
	}
	followDeltas := counterDeltas(follow, "owner-a", "owner-b")
	if followDeltas["owner-a"].following != 1 ||
		followDeltas["owner-b"].followers != 1 {
		t.Fatalf("unexpected follow deltas: %#v", followDeltas)
	}

	follow.Payload.Following = false
	unfollowDeltas := counterDeltas(follow, "owner-a", "owner-b")
	if unfollowDeltas["owner-a"].following != -1 ||
		unfollowDeltas["owner-b"].followers != -1 {
		t.Fatalf("unexpected unfollow deltas: %#v", unfollowDeltas)
	}
}

func TestCounterDeltas_BlockPreservesClearedDirectionIdentity(t *testing.T) {
	event := relmodel.OutboxEvent{
		EventName: relevent.PersonaBlocked,
		Payload: relmodel.OutboxPayload{
			SourceFollowCleared: true,
			TargetFollowCleared: true,
			OccurredAt:          time.Now().UTC(),
		},
	}
	deltas := counterDeltas(event, "owner-a", "owner-b")
	if deltas["owner-a"].followers != -1 ||
		deltas["owner-a"].following != -1 ||
		deltas["owner-b"].followers != -1 ||
		deltas["owner-b"].following != -1 {
		t.Fatalf("mutual block must clear both directions exactly once: %#v", deltas)
	}
}
