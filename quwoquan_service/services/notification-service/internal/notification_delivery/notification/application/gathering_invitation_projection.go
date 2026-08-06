package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"

	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification/domain"
)

const (
	gatheringInvitationSource = "gathering_invitation"
	gatheringInvitationTitle  = "活动邀请"
)

type GatheringInvitationProjection struct {
	store notification.GatheringInvitationProjectionStore
}

func NewGatheringInvitationProjection(
	store notification.GatheringInvitationProjectionStore,
) (*GatheringInvitationProjection, error) {
	if store == nil {
		return nil, errors.New("Gathering invitation projection store is required")
	}
	return &GatheringInvitationProjection{store: store}, nil
}

func (projection *GatheringInvitationProjection) Handle(
	ctx context.Context,
	event InteractionStreamEvent,
) error {
	switch event.EventType {
	case "GatheringInvitationChanged":
		message, err := gatheringInvitationMessage(event)
		if err != nil {
			return err
		}
		_, _, err = projection.store.UpsertGatheringInvitation(ctx, message)
		return err
	case "GatheringCancelled":
		var payload struct {
			GatheringID    string    `json:"gatheringId"`
			LifecycleState string    `json:"lifecycleStatus"`
			OccurredAt     time.Time `json:"occurredAt"`
		}
		if err := decodeInteractionPayload(event.Payload, &payload); err != nil {
			return fmt.Errorf("decode Gathering cancellation payload: %w", err)
		}
		if strings.TrimSpace(payload.GatheringID) == "" ||
			payload.LifecycleState != "cancelled" {
			return errors.New("Gathering cancellation payload is incomplete")
		}
		return projection.store.CancelGatheringInvitations(
			ctx,
			payload.GatheringID,
		)
	default:
		return nil
	}
}

func gatheringInvitationMessage(
	event InteractionStreamEvent,
) (notification.AppMessage, error) {
	var payload struct {
		GatheringID        string `json:"gatheringId"`
		InviterPersonaID   string `json:"inviterPersonaId"`
		RecipientPersonaID string `json:"recipientPersonaId"`
		PurposeSummary     string `json:"purposeSummary"`
		Schedule           struct {
			Timezone  string     `json:"timezone"`
			StartAt   *time.Time `json:"startAt"`
			EndAt     *time.Time `json:"endAt"`
			DateLabel string     `json:"dateLabel"`
		} `json:"schedule"`
		Place struct {
			Mode              string `json:"mode"`
			CoarsePlaceLabel  string `json:"coarsePlaceLabel"`
			ExactMeetingPoint string `json:"exactMeetingPoint"`
		} `json:"place"`
		ParticipationVersion int64  `json:"participationVersion"`
		Status               string `json:"status"`
		ActionIntents        []struct {
			Action                       string `json:"action"`
			ExpectedGatheringVersion     int64  `json:"expectedGatheringVersion"`
			ExpectedParticipationVersion int64  `json:"expectedParticipationVersion"`
		} `json:"actionIntents"`
		ExpiresAt  *time.Time `json:"expiresAt"`
		OccurredAt time.Time  `json:"occurredAt"`
	}
	if err := decodeInteractionPayload(event.Payload, &payload); err != nil {
		return notification.AppMessage{},
			fmt.Errorf("decode Gathering invitation payload: %w", err)
	}
	payload.GatheringID = strings.TrimSpace(payload.GatheringID)
	payload.InviterPersonaID = strings.TrimSpace(payload.InviterPersonaID)
	payload.RecipientPersonaID = strings.TrimSpace(payload.RecipientPersonaID)
	if payload.GatheringID == "" || payload.InviterPersonaID == "" ||
		payload.RecipientPersonaID == "" || payload.ParticipationVersion <= 0 ||
		!validInvitationStatus(payload.Status) {
		return notification.AppMessage{}, errors.New(
			"Gathering invitation identity or status is incomplete",
		)
	}
	if payload.Status != "pending" && len(payload.ActionIntents) != 0 {
		return notification.AppMessage{}, errors.New(
			"terminal Gathering invitation cannot carry action intents",
		)
	}
	intents := make(
		[]notification.AppMessageGatheringInvitationActionIntent,
		0,
		len(payload.ActionIntents),
	)
	for _, intent := range payload.ActionIntents {
		if (intent.Action != "accept" && intent.Action != "decline") ||
			intent.ExpectedGatheringVersion <= 0 ||
			intent.ExpectedParticipationVersion != payload.ParticipationVersion {
			return notification.AppMessage{}, errors.New(
				"Gathering invitation action intent is invalid",
			)
		}
		intents = append(intents,
			notification.AppMessageGatheringInvitationActionIntent{
				Action:                       intent.Action,
				ExpectedGatheringVersion:     intent.ExpectedGatheringVersion,
				ExpectedParticipationVersion: intent.ExpectedParticipationVersion,
			},
		)
	}
	occurredAt := payload.OccurredAt.UTC()
	if occurredAt.IsZero() {
		occurredAt = event.OccurredAt.UTC()
	}
	purposeSummary := strings.TrimSpace(payload.PurposeSummary)
	summary := purposeSummary
	if summary == "" {
		summary = "你收到一条活动邀请"
	}
	key := strings.Join(
		[]string{payload.GatheringID, payload.RecipientPersonaID},
		"\x1f",
	)
	digest := sha256.Sum256([]byte(key))
	stableID := "gathering-invitation-" + hex.EncodeToString(digest[:])
	return notification.AppMessage{
		MessageID:      stableID,
		IdempotencyKey: stableID,
		UserID:         payload.RecipientPersonaID,
		MessageType:    "circle",
		Source:         gatheringInvitationSource,
		SourceID:       payload.GatheringID,
		Destination: notification.AppMessageDestination{
			Type: "user",
			ID:   payload.RecipientPersonaID,
		},
		Title:   gatheringInvitationTitle,
		Summary: summary,
		Target: notification.AppMessageTarget{
			TargetType: "gathering",
			TargetID:   payload.GatheringID,
			Query:      notification.AppMessageRouteQuery{},
		},
		GatheringInvitation: &notification.AppMessageGatheringInvitation{
			GatheringID:        payload.GatheringID,
			InviterPersonaID:   payload.InviterPersonaID,
			RecipientPersonaID: payload.RecipientPersonaID,
			PurposeSummary:     purposeSummary,
			Schedule: notification.AppMessageGatheringInvitationSchedule{
				Timezone:  strings.TrimSpace(payload.Schedule.Timezone),
				StartAt:   payload.Schedule.StartAt,
				EndAt:     payload.Schedule.EndAt,
				DateLabel: strings.TrimSpace(payload.Schedule.DateLabel),
			},
			Place: notification.AppMessageGatheringInvitationPlace{
				Mode:              strings.TrimSpace(payload.Place.Mode),
				CoarsePlaceLabel:  strings.TrimSpace(payload.Place.CoarsePlaceLabel),
				ExactMeetingPoint: strings.TrimSpace(payload.Place.ExactMeetingPoint),
			},
			ParticipationVersion: payload.ParticipationVersion,
			Status:               payload.Status,
			ActionIntents:        intents,
			ExpiresAt:            payload.ExpiresAt,
		},
		CreatedAt: occurredAt,
	}, nil
}

func validInvitationStatus(status string) bool {
	switch status {
	case "pending", "accepted", "declined", "revoked", "cancelled", "expired":
		return true
	default:
		return false
	}
}
