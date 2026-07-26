package model

import (
	"errors"
	"strings"
	"time"
)

const (
	StatusGenerated = "generated"
	StatusDelivered = "delivered"
	StatusViewed    = "viewed"
	StatusAccepted  = "accepted"
	StatusActivated = "activated"
	StatusExpired   = "expired"
	StatusRevoked   = "revoked"
)

var (
	ErrExpired           = errors.New("invitation expired")
	ErrInvalidTransition = errors.New("invalid invitation transition")
)

// Invitation 是独立邀请归因聚合；审计字段通过 json:"-" 永不进入 HTTP 响应。
type Invitation struct {
	ID                    string     `json:"id"`
	InviterSubAccountID   string     `json:"inviterSubAccountId"`
	InviterOwnerAccountID string     `json:"-"`
	Channel               string     `json:"channel"`
	LinkCode              string     `json:"linkCode"`
	InviteePhoneHash      string     `json:"-"`
	Status                string     `json:"status"`
	ExpireAt              time.Time  `json:"expireAt"`
	GeneratedAt           time.Time  `json:"generatedAt"`
	DeliveredAt           *time.Time `json:"-"`
	ViewedAt              *time.Time `json:"-"`
	AcceptedAt            *time.Time `json:"acceptedAt,omitempty"`
	ConvertedAt           *time.Time `json:"convertedAt,omitempty"`
}

func (invitation *Invitation) ValidateNew() error {
	if strings.TrimSpace(invitation.ID) == "" ||
		strings.TrimSpace(invitation.InviterSubAccountID) == "" ||
		strings.TrimSpace(invitation.InviterOwnerAccountID) == "" ||
		strings.TrimSpace(invitation.Channel) == "" ||
		strings.TrimSpace(invitation.LinkCode) == "" ||
		invitation.ExpireAt.IsZero() || invitation.GeneratedAt.IsZero() {
		return ErrInvalidTransition
	}
	if invitation.Status != StatusGenerated ||
		!invitation.ExpireAt.After(invitation.GeneratedAt) {
		return ErrInvalidTransition
	}
	return nil
}

func (invitation *Invitation) MarkDelivered(now time.Time) error {
	if invitation.expire(now) {
		return ErrExpired
	}
	switch invitation.Status {
	case StatusGenerated:
		at := now.UTC()
		invitation.Status = StatusDelivered
		invitation.DeliveredAt = &at
		return nil
	case StatusDelivered, StatusViewed, StatusAccepted, StatusActivated:
		return nil
	default:
		return ErrInvalidTransition
	}
}

func (invitation *Invitation) Accept(now time.Time) error {
	if invitation.expire(now) {
		return ErrExpired
	}
	switch invitation.Status {
	case StatusGenerated, StatusDelivered, StatusViewed:
		at := now.UTC()
		invitation.Status = StatusAccepted
		invitation.AcceptedAt = &at
		return nil
	case StatusAccepted, StatusActivated:
		return nil
	default:
		return ErrInvalidTransition
	}
}

func (invitation *Invitation) ProjectExpiry(now time.Time) {
	invitation.expire(now)
}

func (invitation *Invitation) expire(now time.Time) bool {
	if invitation.Status == StatusExpired {
		return true
	}
	if invitation.Status == StatusRevoked {
		return false
	}
	if !now.UTC().Before(invitation.ExpireAt.UTC()) &&
		invitation.Status != StatusAccepted &&
		invitation.Status != StatusActivated {
		invitation.Status = StatusExpired
		return true
	}
	return false
}
