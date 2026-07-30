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

type Channel string

const (
	ChannelSystemShare   Channel = "system_share"
	ChannelWechatFriend  Channel = "wechat_friend"
	ChannelWechatMoments Channel = "wechat_moments"
)

func (value Channel) Valid() bool {
	return value == ChannelSystemShare ||
		value == ChannelWechatFriend ||
		value == ChannelWechatMoments
}

type DestinationKind string

const DestinationKindExternalApp DestinationKind = "external_app"

func (value DestinationKind) Valid() bool {
	return value == DestinationKindExternalApp
}

type Fact struct {
	EventID           string
	PostID            string
	ActorDimension    ActorDimension
	ActorID           string
	Channel           Channel
	DestinationKind   DestinationKind
	DestinationDigest string
	ReferralID        string
	IdempotencyKey    string
	OccurredAt        time.Time
}

func (f Fact) Validate() error {
	if strings.TrimSpace(f.EventID) == "" ||
		strings.TrimSpace(f.PostID) == "" ||
		strings.TrimSpace(f.ActorID) == "" ||
		strings.TrimSpace(string(f.Channel)) == "" ||
		strings.TrimSpace(string(f.DestinationKind)) == "" ||
		strings.TrimSpace(f.ReferralID) == "" ||
		strings.TrimSpace(f.IdempotencyKey) == "" ||
		f.OccurredAt.IsZero() {
		return errors.New("outbound share fact requires event, post, actor, channel, destination kind, referral, idempotency key and occurredAt")
	}
	if f.ActorDimension != ActorDimensionPersona && f.ActorDimension != ActorDimensionDevice {
		return errors.New("outbound share actor dimension must be persona or device")
	}
	if !f.Channel.Valid() {
		return errors.New("outbound share channel is invalid")
	}
	if !f.DestinationKind.Valid() {
		return errors.New("outbound share destination kind is invalid")
	}
	return nil
}
