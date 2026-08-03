package model

import (
	"errors"
	"strings"
	"time"
)

const SessionTTL = 120 * time.Second

type Identity struct {
	AccountID string
	PersonaID string
	DeviceID  string
}

type Session struct {
	ConnectionID string
	Identity     Identity
	AuthEpoch    int64
	Transport    string
	Fence        int64
	StartedAt    time.Time
	ExpiresAt    time.Time
}

func StartSession(
	connectionID string,
	identity Identity,
	authEpoch int64,
	transport string,
	fence int64,
	startedAt time.Time,
) (*Session, error) {
	session := &Session{
		ConnectionID: strings.TrimSpace(connectionID),
		Identity: Identity{
			AccountID: strings.TrimSpace(identity.AccountID),
			PersonaID: strings.TrimSpace(identity.PersonaID),
			DeviceID:  strings.TrimSpace(identity.DeviceID),
		},
		AuthEpoch: authEpoch,
		Transport: strings.TrimSpace(transport),
		Fence:     fence,
		StartedAt: startedAt.UTC(),
		ExpiresAt: startedAt.UTC().Add(SessionTTL),
	}
	if err := session.Validate(); err != nil {
		return nil, err
	}
	return session, nil
}

func (session *Session) Validate() error {
	if session == nil || session.ConnectionID == "" ||
		session.Identity.AccountID == "" || session.Identity.PersonaID == "" ||
		session.Identity.DeviceID == "" || session.AuthEpoch <= 0 ||
		session.Transport == "" || session.Fence <= 0 ||
		session.StartedAt.IsZero() || !session.ExpiresAt.After(session.StartedAt) {
		return errors.New("realtime connection session is invalid")
	}
	return nil
}

// Renew is valid only while the authenticated session is still live. An
// expired runtime session must be replaced by a newly authenticated session;
// it cannot be revived by a late heartbeat.
func (session *Session) Renew(authenticatedAt time.Time) error {
	if err := session.Validate(); err != nil {
		return err
	}
	authenticatedAt = authenticatedAt.UTC()
	if !authenticatedAt.Before(session.ExpiresAt) {
		return errors.New("realtime connection session expired")
	}
	session.ExpiresAt = authenticatedAt.Add(SessionTTL)
	return nil
}
