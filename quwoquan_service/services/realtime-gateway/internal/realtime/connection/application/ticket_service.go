package application

import (
	"context"
	"errors"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
)

const defaultTicketTTL = 30 * time.Second

// TicketService 是 IssueConnectionTicket 的 session facade：
// Bearer 重建的可信身份换取短期一次性 ticket，WS 升级 query 只携带该 ticket。
type TicketService struct {
	store     TicketStore
	authority rtauth.AccountSecurityAuthority
	security  AccountSecurityGate
	ttl       time.Duration
	now       func() time.Time
}

func NewTicketService(
	store TicketStore,
	authority rtauth.AccountSecurityAuthority,
	security AccountSecurityGate,
) (*TicketService, error) {
	if store == nil || authority == nil || security == nil {
		return nil, errors.New(
			"realtime ticket service requires store, account security authority and gate",
		)
	}
	return &TicketService{
		store:     store,
		authority: authority,
		security:  security,
		ttl:       defaultTicketTTL,
		now:       time.Now,
	}, nil
}

type IssuedTicket struct {
	Ticket    string    `json:"ticket"`
	ExpiresAt time.Time `json:"expiresAt"`
}

func (s *TicketService) Issue(
	ctx context.Context,
	identity TrustedIdentity,
	authEpoch int64,
) (IssuedTicket, error) {
	identity.AccountID = strings.TrimSpace(identity.AccountID)
	identity.PersonaID = strings.TrimSpace(identity.PersonaID)
	identity.DeviceID = strings.TrimSpace(identity.DeviceID)
	if identity.AccountID == "" ||
		identity.PersonaID == "" ||
		identity.DeviceID == "" {
		return IssuedTicket{}, errors.New(
			"realtime ticket requires trusted account, persona and device identities",
		)
	}
	if authEpoch <= 0 {
		return IssuedTicket{}, ErrAccountSecurityDenied
	}
	if err := VerifyAccountSecurity(
		ctx,
		s.authority,
		identity.AccountID,
		authEpoch,
	); err != nil {
		return IssuedTicket{}, err
	}
	if err := s.security.Admit(ctx, identity, authEpoch); err != nil {
		return IssuedTicket{}, err
	}
	now := s.now().UTC()
	ticket, err := s.store.Issue(ctx, TicketClaims{
		TrustedIdentity: identity,
		AuthEpoch:       authEpoch,
		IssuedAt:        now.Unix(),
	}, s.ttl)
	if err != nil {
		return IssuedTicket{}, err
	}
	// A terminal event may have advanced the Redis gate while Issue wrote the
	// one-time key. Recheck and revoke this specific key rather than leaving a
	// post-close reconnect window until TTL expiry.
	if err := s.security.Admit(ctx, identity, authEpoch); err != nil {
		_ = s.store.Revoke(ctx, identity.AccountID, ticket)
		return IssuedTicket{}, err
	}
	return IssuedTicket{Ticket: ticket, ExpiresAt: now.Add(s.ttl)}, nil
}

// Consume 校验并一次性消费 ticket，返回其绑定的可信身份。
func (s *TicketService) Consume(ctx context.Context, ticket string) (TicketClaims, error) {
	ticket = strings.TrimSpace(ticket)
	if ticket == "" {
		return TicketClaims{}, ErrTicketInvalid
	}
	claims, err := s.store.Consume(ctx, ticket)
	if err != nil {
		return TicketClaims{}, err
	}
	if err := VerifyAccountSecurity(
		ctx,
		s.authority,
		claims.AccountID,
		claims.AuthEpoch,
	); err != nil {
		return TicketClaims{}, err
	}
	if err := s.security.Admit(
		ctx,
		claims.TrustedIdentity,
		claims.AuthEpoch,
	); err != nil {
		return TicketClaims{}, err
	}
	return claims, nil
}
