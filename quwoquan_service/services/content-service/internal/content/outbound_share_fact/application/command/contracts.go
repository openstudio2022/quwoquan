package command

import (
	"context"
	"time"

	sharemodel "quwoquan_service/services/content-service/internal/content/outbound_share_fact/domain/model"
)

type AppendOutboundShareCommand struct {
	PostID            string
	ActorDimension    sharemodel.ActorDimension
	ActorID           string
	Channel           string
	DestinationKind   string
	Destination       string
	ReferralID        string
	DeliverySucceeded bool
	ProviderReceiptID string
	ClientConfirmedAt time.Time
}

type AppendOutboundShareResult struct {
	EventID    string    `json:"eventId"`
	PostID     string    `json:"postId"`
	Channel    string    `json:"channel"`
	ReferralID string    `json:"referralId"`
	OccurredAt time.Time `json:"occurredAt"`
	Replayed   bool      `json:"replayed"`
}

type ShareablePostSlice struct {
	PostID string
	Status string
}

type ShareablePostReader interface {
	FindShareablePost(context.Context, string) (ShareablePostSlice, bool, error)
}
