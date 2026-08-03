package accountclosure

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	closuremodel "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/domain/model"
)

const (
	UserAccountEventStream = "events.user.account"
	UserAccountClosedName  = closuremodel.UserAccountClosedName
	ConsumerGroup          = "content-service-user-account-closed"
	DeadLetterStream       = "events.user.account.content-service.dlq"
)

var ErrUnsupportedEvent = errors.New("unsupported user account event")

type UserAccountClosedPayload = closuremodel.UserAccountClosedPayload
type UserAccountClosedEvent = closuremodel.UserAccountClosedEvent

func DecodeUserAccountClosedEvent(message rtredis.StreamMessage) (UserAccountClosedEvent, error) {
	values := message.Values
	eventName := strings.TrimSpace(values["eventName"])
	if eventName != UserAccountClosedName {
		return UserAccountClosedEvent{}, fmt.Errorf("%w: %q", ErrUnsupportedEvent, eventName)
	}
	accountVersion, err := strconv.ParseInt(strings.TrimSpace(values["accountVersion"]), 10, 64)
	if err != nil || accountVersion <= 0 {
		return UserAccountClosedEvent{}, errors.New("UserAccountClosed accountVersion is invalid")
	}
	occurredAt, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(values["occurredAt"]))
	if err != nil {
		return UserAccountClosedEvent{}, errors.New("UserAccountClosed occurredAt is invalid")
	}
	var rawPayload struct {
		UserID       string   `json:"userId"`
		PersonaIDs   []string `json:"personaIds"`
		AccountState string   `json:"accountState"`
		UpdatedAt    string   `json:"updatedAt"`
	}
	if err := json.Unmarshal([]byte(values["payload"]), &rawPayload); err != nil {
		return UserAccountClosedEvent{}, errors.New("UserAccountClosed payload is invalid")
	}
	if rawPayload.PersonaIDs == nil {
		return UserAccountClosedEvent{}, errors.New("UserAccountClosed personaIds is missing")
	}
	updatedAt, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(rawPayload.UpdatedAt))
	if err != nil {
		return UserAccountClosedEvent{}, errors.New("UserAccountClosed payload updatedAt is invalid")
	}
	event := UserAccountClosedEvent{
		EventID:        strings.TrimSpace(values["eventId"]),
		EventName:      eventName,
		AccountID:      strings.TrimSpace(values["accountId"]),
		AccountVersion: accountVersion,
		Payload: UserAccountClosedPayload{
			UserID:       strings.TrimSpace(rawPayload.UserID),
			PersonaIDs:   closuremodel.NormalizeSubjectIDs(rawPayload.PersonaIDs),
			AccountState: strings.TrimSpace(rawPayload.AccountState),
			UpdatedAt:    updatedAt.UTC(),
		},
		OccurredAt: occurredAt.UTC(),
	}
	if err := event.Validate(); err != nil {
		return UserAccountClosedEvent{}, err
	}
	return event, nil
}

func irreversibleDigest(value string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(sum[:])
}
