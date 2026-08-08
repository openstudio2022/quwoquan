package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strconv"
	"strings"

	"quwoquan_service/services/rtc-service/generated/rtc/call_session"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application/commandmeta"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/domain/model"
)

func participantOf(session *model.CallSession, userID string) *model.Participant {
	for i := range session.Participants {
		if session.Participants[i].UserID == userID {
			return &session.Participants[i]
		}
	}
	return nil
}

func commandDigest(commandName string, payload any) string {
	body, _ := json.Marshal(payload)
	sum := sha256.Sum256(append([]byte(commandName+"\x00"), body...))
	return hex.EncodeToString(sum[:])
}

func canonicalInviteeIDs(actorID string, values []string) ([]string, error) {
	if len(values) == 0 {
		return nil, errors.New("at least one inviteeId is required")
	}
	actorID = strings.TrimSpace(actorID)
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, raw := range values {
		value := strings.TrimSpace(raw)
		if value == "" {
			return nil, errors.New("inviteeId must not be empty")
		}
		if value == actorID {
			return nil, errors.New("actor cannot invite itself")
		}
		if _, exists := seen[value]; exists {
			return nil, errors.New("inviteeIds must not contain duplicates")
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	return result, nil
}

func scopedIdempotencyKey(ctx context.Context, actorID string) (string, error) {
	raw := strings.TrimSpace(commandmeta.IdempotencyKey(ctx))
	if raw == "" {
		return "", generated.AppErrorFromInternalError("call command requires Idempotency-Key")
	}
	sum := sha256.Sum256([]byte(strings.TrimSpace(actorID) + "\x00" + raw))
	return "rtc-call:" + hex.EncodeToString(sum[:]), nil
}

func eventIdentifier(
	callID string,
	eventType string,
	version int64,
	targetPersonaID string,
) string {
	sum := sha256.Sum256([]byte(
		callID + "\x00" +
			eventType + "\x00" +
			strconv.FormatInt(version, 10) + "\x00" +
			strings.TrimSpace(targetPersonaID),
	))
	return "rtc-evt-" + hex.EncodeToString(sum[:16])
}

func incomingCallDeliveryKey(callID string, targetPersonaID string) string {
	sum := sha256.Sum256([]byte(
		strings.TrimSpace(callID) + "\x00" +
			strings.TrimSpace(targetPersonaID),
	))
	return "sha256:" + hex.EncodeToString(sum[:])
}

func callSourceLabel(session *model.CallSession) string {
	if session == nil {
		return "direct_call"
	}
	if strings.TrimSpace(session.CircleID) != "" {
		return "circle"
	}
	if strings.TrimSpace(session.ConversationID) != "" {
		return "conversation"
	}
	return "direct_call"
}

func callTrustRelation(session *model.CallSession) string {
	if session != nil &&
		session.MaxParticipants <= model.MaxParticipants1v1 {
		return "known"
	}
	return "possibly_unknown"
}
