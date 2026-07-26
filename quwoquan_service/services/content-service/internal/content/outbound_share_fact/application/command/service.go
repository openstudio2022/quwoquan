package command

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"strings"
	"time"

	sharemodel "quwoquan_service/services/content-service/internal/content/outbound_share_fact/domain/model"
	shareports "quwoquan_service/services/content-service/internal/content/outbound_share_fact/domain/ports"
	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
)

type Service struct {
	sink       shareports.AppendSink
	postReader ShareablePostReader
	now        func() time.Time
	newEventID func() (string, error)
}

func NewService(sink shareports.AppendSink, postReader ShareablePostReader) *Service {
	if sink == nil || postReader == nil {
		panic("OutboundShareFact service requires append sink and shareable Post reader")
	}
	return &Service{sink: sink, postReader: postReader, now: time.Now, newEventID: newOutboundShareEventID}
}

func (s *Service) AppendOutboundShare(ctx context.Context, command AppendOutboundShareCommand) (AppendOutboundShareResult, error) {
	command = normalizeCommand(command)
	if err := validateCommand(command); err != nil {
		return AppendOutboundShareResult{}, contentgenerated.AppErrorFromInvalidArgument(err.Error())
	}
	post, found, err := s.postReader.FindShareablePost(ctx, command.PostID)
	if err != nil {
		return AppendOutboundShareResult{}, contentgenerated.AppErrorFromStorageWriteFailed(err.Error())
	}
	if !found || strings.EqualFold(post.Status, "deleted") {
		return AppendOutboundShareResult{}, contentgenerated.AppErrorFromPostNotFound("outbound share target is missing or deleted")
	}
	idempotencyKey := strings.TrimSpace(commandmeta.IdempotencyKey(ctx))
	if idempotencyKey == "" {
		return AppendOutboundShareResult{}, contentgenerated.AppErrorFromIdempotencyConflict("CreateOutboundShare requires Idempotency-Key")
	}
	eventID, err := s.newEventID()
	if err != nil {
		return AppendOutboundShareResult{}, contentgenerated.AppErrorFromStorageWriteFailed(err.Error())
	}
	occurredAt := s.now().UTC()
	if !command.ClientConfirmedAt.IsZero() && command.ClientConfirmedAt.Before(occurredAt) {
		occurredAt = command.ClientConfirmedAt.UTC()
	}
	fact := sharemodel.Fact{
		EventID: eventID, PostID: command.PostID, ActorDimension: command.ActorDimension,
		ActorID: command.ActorID, Channel: command.Channel, DestinationKind: command.DestinationKind,
		DestinationDigest: digestDestination(command.Destination), ReferralID: command.ReferralID,
		IdempotencyKey: idempotencyKey, OccurredAt: occurredAt,
	}
	if err := fact.Validate(); err != nil {
		return AppendOutboundShareResult{}, contentgenerated.AppErrorFromInvalidArgument(err.Error())
	}
	digest, err := outboundShareCommandDigest(fact, command.ProviderReceiptID)
	if err != nil {
		return AppendOutboundShareResult{}, contentgenerated.AppErrorFromStorageWriteFailed(err.Error())
	}
	payload, err := outboundShareEventPayload(fact, command.ProviderReceiptID)
	if err != nil {
		return AppendOutboundShareResult{}, contentgenerated.AppErrorFromStorageWriteFailed(err.Error())
	}
	stored, err := s.sink.Append(ctx, shareports.AppendRequest{
		Fact: fact, CommandDigest: digest,
		Outbox: shareports.OutboxEvent{EventID: eventID, EventType: "OutboundShareRecorded", Payload: payload, OccurredAt: occurredAt},
	})
	if err != nil {
		return AppendOutboundShareResult{}, contentgenerated.AppErrorFromStorageWriteFailed(err.Error())
	}
	return resultFromFact(stored.Fact, stored.Replayed), nil
}

func normalizeCommand(command AppendOutboundShareCommand) AppendOutboundShareCommand {
	command.PostID = strings.TrimSpace(command.PostID)
	command.ActorID = strings.TrimSpace(command.ActorID)
	command.Channel = strings.TrimSpace(command.Channel)
	command.DestinationKind = strings.TrimSpace(command.DestinationKind)
	command.Destination = strings.TrimSpace(command.Destination)
	command.ReferralID = strings.TrimSpace(command.ReferralID)
	command.ProviderReceiptID = strings.TrimSpace(command.ProviderReceiptID)
	return command
}

func validateCommand(command AppendOutboundShareCommand) error {
	if !command.DeliverySucceeded || command.ProviderReceiptID == "" {
		return &validationError{"outbound share requires a successful provider receipt"}
	}
	if command.PostID == "" || command.ActorID == "" || command.Channel == "" || command.DestinationKind == "" || command.ReferralID == "" {
		return &validationError{"postId, trusted actor, channel, destinationKind and referralId are required"}
	}
	if command.ActorDimension != sharemodel.ActorDimensionPersona && command.ActorDimension != sharemodel.ActorDimensionDevice {
		return &validationError{"actor dimension must be persona or device"}
	}
	return nil
}

type validationError struct{ message string }

func (e *validationError) Error() string { return e.message }

func digestDestination(destination string) string {
	if destination == "" {
		return ""
	}
	sum := sha256.Sum256([]byte(destination))
	return hex.EncodeToString(sum[:])
}

func outboundShareCommandDigest(fact sharemodel.Fact, providerReceiptID string) (string, error) {
	payload, err := json.Marshal(struct {
		PostID                string                    `json:"postId"`
		ActorDimension        sharemodel.ActorDimension `json:"actorDimension"`
		ActorID               string                    `json:"actorId"`
		Channel               string                    `json:"channel"`
		DestinationKind       string                    `json:"destinationKind"`
		DestinationDigest     string                    `json:"destinationDigest,omitempty"`
		ReferralID            string                    `json:"referralId"`
		ProviderReceiptDigest string                    `json:"providerReceiptDigest"`
	}{
		fact.PostID, fact.ActorDimension, fact.ActorID, fact.Channel,
		fact.DestinationKind, fact.DestinationDigest, fact.ReferralID,
		digestDestination(providerReceiptID),
	})
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:]), nil
}

func outboundShareEventPayload(fact sharemodel.Fact, providerReceiptID string) ([]byte, error) {
	payload, err := json.Marshal(struct {
		EventID               string                    `json:"eventId"`
		PostID                string                    `json:"postId"`
		ActorDimension        sharemodel.ActorDimension `json:"actorDimension"`
		ActorID               string                    `json:"actorId"`
		Channel               string                    `json:"channel"`
		DestinationKind       string                    `json:"destinationKind"`
		DestinationDigest     string                    `json:"destinationDigest,omitempty"`
		ReferralID            string                    `json:"referralId"`
		ProviderReceiptDigest string                    `json:"providerReceiptDigest"`
		OccurredAt            time.Time                 `json:"occurredAt"`
	}{fact.EventID, fact.PostID, fact.ActorDimension, fact.ActorID, fact.Channel, fact.DestinationKind, fact.DestinationDigest, fact.ReferralID, digestDestination(providerReceiptID), fact.OccurredAt})
	return payload, err
}

func resultFromFact(fact sharemodel.Fact, replayed bool) AppendOutboundShareResult {
	return AppendOutboundShareResult{EventID: fact.EventID, PostID: fact.PostID, Channel: fact.Channel, ReferralID: fact.ReferralID, OccurredAt: fact.OccurredAt, Replayed: replayed}
}

func newOutboundShareEventID() (string, error) {
	var raw [16]byte
	if _, err := rand.Read(raw[:]); err != nil {
		return "", err
	}
	return "osf_" + hex.EncodeToString(raw[:]), nil
}
