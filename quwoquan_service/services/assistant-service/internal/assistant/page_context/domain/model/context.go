package model

import (
	"errors"
	"strings"
	"time"
)

const TTL = 5 * time.Minute

type ObjectRef struct {
	ObjectTypeRef string `json:"objectTypeRef"`
	ObjectID      string `json:"objectId"`
}

type Action struct {
	ActionType    string `json:"actionType"`
	ObjectTypeRef string `json:"objectTypeRef,omitempty"`
	ObjectID      string `json:"objectId,omitempty"`
}

type Snapshot struct {
	CapturedAt     time.Time   `json:"capturedAt"`
	PageType       string      `json:"pageType"`
	PageObjects    []ObjectRef `json:"pageObjects"`
	UserActions    []Action    `json:"userActions"`
	ConsentGranted bool        `json:"consentGranted"`
}

type PageContext struct {
	AccountID  string    `json:"accountId"`
	PersonaID  string    `json:"personaId"`
	Snapshot   Snapshot  `json:"contextSnapshot"`
	CapturedAt time.Time `json:"capturedAt"`
	ExpiresAt  time.Time `json:"expiresAt"`
}

type Receipt struct {
	Accepted   bool      `json:"accepted"`
	ContextKey string    `json:"contextKey"`
	ExpiresAt  time.Time `json:"expiresAt"`
}

func New(accountID, personaID string, snapshot Snapshot, now time.Time) (PageContext, error) {
	accountID = strings.TrimSpace(accountID)
	personaID = strings.TrimSpace(personaID)
	if accountID == "" || personaID == "" {
		return PageContext{}, errors.New("trusted accountId and personaId are required")
	}
	now = now.UTC()
	snapshot.CapturedAt = snapshot.CapturedAt.UTC()
	if snapshot.CapturedAt.IsZero() || snapshot.CapturedAt.Before(now.Add(-TTL)) || snapshot.CapturedAt.After(now.Add(time.Minute)) {
		return PageContext{}, errors.New("capturedAt is outside the accepted freshness window")
	}
	if strings.TrimSpace(snapshot.PageType) == "" {
		return PageContext{}, errors.New("pageType is required")
	}
	if !snapshot.ConsentGranted && (len(snapshot.PageObjects) > 0 || len(snapshot.UserActions) > 0) {
		return PageContext{}, errors.New("page context consent is required")
	}
	if len(snapshot.PageObjects) > 20 || len(snapshot.UserActions) > 20 {
		return PageContext{}, errors.New("page context exceeds its bounded capacity")
	}
	for _, object := range snapshot.PageObjects {
		if strings.TrimSpace(object.ObjectTypeRef) == "" || strings.TrimSpace(object.ObjectID) == "" {
			return PageContext{}, errors.New("page object requires objectTypeRef and objectId")
		}
	}
	for _, action := range snapshot.UserActions {
		if strings.TrimSpace(action.ActionType) == "" || ((strings.TrimSpace(action.ObjectTypeRef) == "") != (strings.TrimSpace(action.ObjectID) == "")) {
			return PageContext{}, errors.New("page action is invalid")
		}
	}
	return PageContext{
		AccountID:  accountID,
		PersonaID:  personaID,
		Snapshot:   snapshot,
		CapturedAt: snapshot.CapturedAt,
		ExpiresAt:  now.Add(TTL),
	}, nil
}

func StorageKey(accountID string) string {
	return "assistant:page-context:" + strings.TrimSpace(accountID)
}
