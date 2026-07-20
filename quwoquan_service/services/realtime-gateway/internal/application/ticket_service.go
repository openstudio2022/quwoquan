package application

import (
	"context"
	"errors"
	"strings"
	"time"
)

const defaultTicketTTL = 30 * time.Second

// TicketService 是 IssueConnectionTicket 的 session facade：
// Bearer 重建的可信身份换取短期一次性 ticket，WS 升级 query 只携带该 ticket。
type TicketService struct {
	store TicketStore
	ttl   time.Duration
	now   func() time.Time
}

func NewTicketService(store TicketStore) (*TicketService, error) {
	if store == nil {
		return nil, errors.New("realtime ticket store is required")
	}
	return &TicketService{store: store, ttl: defaultTicketTTL, now: time.Now}, nil
}

type IssuedTicket struct {
	Ticket    string    `json:"ticket"`
	ExpiresAt time.Time `json:"expiresAt"`
}

func (s *TicketService) Issue(
	ctx context.Context,
	identity TrustedIdentity,
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
	now := s.now().UTC()
	ticket, err := s.store.Issue(ctx, TicketClaims{
		TrustedIdentity: identity,
		IssuedAt:        now.Unix(),
	}, s.ttl)
	if err != nil {
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
	return s.store.Consume(ctx, ticket)
}
