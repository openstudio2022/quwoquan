// Package profileprojection publishes User-owned profile facts for the
// SearchIndexView consumer. It never imports or calls an ES/OpenSearch client.
package profileprojection

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

const (
	UserProfileSearchProjectionStream = "events.user.profile_search"
	userProfileSearchProjectionName   = "UserProfileSearchProjectionRequested"
)

type StreamPublisher struct {
	transport runtimemessaging.MessageTransport
}

func NewStreamPublisher(
	transport runtimemessaging.MessageTransport,
) (*StreamPublisher, error) {
	if transport == nil {
		return nil, errors.New("UserProfile search projection stream requires transport")
	}
	return &StreamPublisher{transport: transport}, nil
}

func (publisher *StreamPublisher) PublishUserProfileSearch(
	ctx context.Context,
	event userports.UserProfileSearchOutboxEvent,
) error {
	if publisher == nil || publisher.transport == nil {
		return errors.New("UserProfile search projection stream is not configured")
	}
	payload, err := decodeProjectionPayload(event)
	if err != nil {
		return err
	}
	canonical, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("encode UserProfile search projection payload: %w", err)
	}
	if _, err := publisher.transport.AppendDurable(
		ctx,
		runtimemessaging.DurableMessage{
			Stream: UserProfileSearchProjectionStream,
			Fields: []runtimemessaging.DurableField{
				{Name: "eventId", Value: payload.EventID},
				{Name: "eventName", Value: userProfileSearchProjectionName},
				{Name: "userId", Value: payload.UserID},
				{Name: "profileVersion", Value: strconv.FormatInt(payload.ProfileVersion, 10)},
				{Name: "payload", Value: string(canonical)},
				{Name: "occurredAt", Value: event.OccurredAt.UTC().Format(time.RFC3339Nano)},
			},
		},
	); err != nil {
		return fmt.Errorf("append UserProfile search projection stream: %w", err)
	}
	return nil
}

func decodeProjectionPayload(
	event userports.UserProfileSearchOutboxEvent,
) (userports.UserProfileSearchProjectionPayload, error) {
	var payload userports.UserProfileSearchProjectionPayload
	if strings.TrimSpace(event.EventID) == "" ||
		strings.TrimSpace(event.UserID) == "" ||
		event.ProfileVersion <= 0 || event.OccurredAt.IsZero() ||
		!json.Valid(event.PayloadJSON) {
		return payload, errors.New("UserProfile search projection event identity is invalid")
	}
	if err := json.Unmarshal(event.PayloadJSON, &payload); err != nil {
		return payload, errors.New("UserProfile search projection payload is invalid")
	}
	if payload.EventID != event.EventID || payload.UserID != event.UserID ||
		payload.ProfileVersion != event.ProfileVersion ||
		(payload.Operation != "upsert" && payload.Operation != "delete") ||
		payload.UpdatedAt.IsZero() || payload.FollowerCount < 0 || payload.PostCount < 0 ||
		payload.IdentityTags == nil {
		return payload, errors.New("UserProfile search projection payload binding is invalid")
	}
	if payload.Operation == "delete" {
		payload.Nickname = ""
		payload.AvatarURL = ""
		payload.Bio = ""
		payload.IdentityTags = []string{}
		payload.FollowerCount = 0
		payload.PostCount = 0
	}
	return payload, nil
}
