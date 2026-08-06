package persistence_test

import (
	"slices"
	"testing"
	"time"

	gatheringevent "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/event"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	persistence "quwoquan_service/services/circle-service/internal/circle_management/gathering/infrastructure/persistence"
)

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-001
func TestGatheringEventPayloadUsesDeclaredEventFields(t *testing.T) {
	now := time.Now().UTC()
	value := model.Gathering{
		ID: "g-1", Version: 2,
		LifecycleStatus:                contract.GatheringLifecycleStatusDraft,
		RoomBindingStatus:              contract.GatheringRoomBindingStatusPending,
		CurrentGatheringRevisionID:     "revision-1",
		CurrentGatheringRevisionNumber: 1,
		Revisions: []contract.GatheringRevision{{
			RevisionID: "revision-1", RevisionNumber: 1,
			Digest: "revision-digest",
		}},
		UpdatedAt: now,
	}
	payload := persistence.GatheringEventPayloadFor(
		gatheringevent.GatheringDraftCreated,
		"persona-owner",
		nil,
		value,
	)
	assertPayloadKeys(t, payload, []string{
		"actorPersonaId", "aggregateVersion", "gatheringId",
		"lifecycleStatus", "occurredAt", "revisionDigest", "revisionId",
		"revisionNumber", "roomBindingStatus",
	})
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-001
func TestGatheringEventPayloadFindsChangedOwnedRow(t *testing.T) {
	now := time.Now().UTC()
	previous := model.Gathering{
		ID: "g-1", Version: 7,
		Participations: []contract.GatheringParticipation{
			{PersonaID: "changed", State: contract.GatheringParticipationStateApplicationPending, Version: 1},
			{PersonaID: "unchanged-last", State: contract.GatheringParticipationStateActive, Version: 4},
		},
		UpdatedAt: now,
	}
	next := previous
	next.Version++
	next.UpdatedAt = now.Add(time.Second)
	next.Participations = append(
		[]contract.GatheringParticipation(nil),
		previous.Participations...,
	)
	next.Participations[0].State = contract.GatheringParticipationStateActive
	next.Participations[0].Version++
	payload := persistence.GatheringEventPayloadFor(
		gatheringevent.GatheringParticipationChanged,
		"persona-host",
		&previous,
		next,
	)
	if payload["participantPersonaId"] != "changed" ||
		payload["participationState"] != contract.GatheringParticipationStateActive {
		t.Fatalf("changed Participation payload=%+v", payload)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-006
func TestGatheringInvitationPayloadIsDisclosureSafeAndActionable(t *testing.T) {
	now := time.Now().UTC()
	previous := model.Gathering{
		ID: "g-invitation", Version: 10,
		LifecycleStatus: contract.GatheringLifecycleStatusPublished,
		Purpose: contract.GatheringPurpose{
			Summary: "一起看展",
		},
		Schedule: contract.GatheringSchedule{
			Timezone: "Asia/Shanghai",
			StartAt:  now.Add(24 * time.Hour),
			EndAt:    now.Add(26 * time.Hour),
		},
		Place: contract.GatheringPlace{
			Mode:              contract.GatheringPlaceModePhysical,
			CoarsePlaceLabel:  "浦东新区",
			ExactMeetingPoint: "私密门牌",
		},
		PolicySet: contract.GatheringPolicySet{
			DisclosurePolicy: contract.GatheringDisclosurePolicy{
				TimeDisclosure:   contract.GatheringTimeDisclosureAfterJoin,
				PlaceDisclosure:  contract.GatheringPlaceDisclosureAfterJoin,
				RosterDisclosure: contract.GatheringRosterDisclosureCountOnly,
			},
		},
		UpdatedAt: now,
	}
	next := previous
	next.Version++
	next.UpdatedAt = now.Add(time.Second)
	next.Participations = []contract.GatheringParticipation{{
		GatheringID: "g-invitation", PersonaID: "persona-recipient",
		InvitedByPersonaID: "persona-inviter",
		State:              contract.GatheringParticipationStateInvitedPending,
		AdmissionSource:    contract.GatheringAdmissionSourceInvitation,
		SeatHoldUntil:      now.Add(time.Hour),
		Version:            1,
	}}
	payload := persistence.GatheringEventPayloadFor(
		gatheringevent.GatheringInvitationChanged,
		"persona-inviter",
		&previous,
		next,
	)
	assertPayloadKeys(t, payload, []string{
		"actionIntents", "expiresAt", "gatheringId", "inviterPersonaId",
		"occurredAt", "participationVersion", "place", "purposeSummary",
		"recipientPersonaId", "schedule", "status",
	})
	if payload["status"] != "pending" {
		t.Fatalf("status=%v", payload["status"])
	}
	schedule := payload["schedule"].(map[string]any)
	if _, leaked := schedule["startAt"]; leaked {
		t.Fatalf("after_join schedule leaked: %+v", schedule)
	}
	place := payload["place"].(map[string]any)
	if _, leaked := place["exactMeetingPoint"]; leaked {
		t.Fatalf("after_join place leaked: %+v", place)
	}
	if _, leaked := place["coarsePlaceLabel"]; leaked {
		t.Fatalf("after_join place leaked: %+v", place)
	}
	intents := payload["actionIntents"].([]map[string]any)
	if len(intents) != 2 {
		t.Fatalf("action intents=%+v", intents)
	}
}

func assertPayloadKeys(
	t *testing.T,
	payload map[string]any,
	want []string,
) {
	t.Helper()
	got := make([]string, 0, len(payload))
	for key := range payload {
		got = append(got, key)
	}
	slices.Sort(got)
	slices.Sort(want)
	if !slices.Equal(got, want) {
		t.Fatalf("payload keys=%v want=%v payload=%+v", got, want, payload)
	}
}
