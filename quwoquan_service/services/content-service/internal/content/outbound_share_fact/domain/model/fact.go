package model

import (
	"errors"
	"strings"
	"time"
)

type ActorDimension string

const (
	ActorDimensionPersona ActorDimension = "persona"
	ActorDimensionDevice  ActorDimension = "device"
)

type Fact struct {
	EventID           string
	PostID            string
	ActorDimension    ActorDimension
	ActorID           string
	Channel           string
	DestinationKind   string
	DestinationDigest string
	ReferralID        string
	IdempotencyKey    string
	OccurredAt        time.Time
}

func (f Fact) Validate() error {
	if strings.TrimSpace(f.EventID) == "" ||
		strings.TrimSpace(f.PostID) == "" ||
		strings.TrimSpace(f.ActorID) == "" ||
		strings.TrimSpace(f.Channel) == "" ||
		strings.TrimSpace(f.DestinationKind) == "" ||
		strings.TrimSpace(f.ReferralID) == "" ||
		strings.TrimSpace(f.IdempotencyKey) == "" ||
		f.OccurredAt.IsZero() {
		return errors.New("outbound share fact requires event, post, actor, channel, destination kind, referral, idempotency key and occurredAt")
	}
	if f.ActorDimension != ActorDimensionPersona && f.ActorDimension != ActorDimensionDevice {
		return errors.New("outbound share actor dimension must be persona or device")
	}
	return nil
}
