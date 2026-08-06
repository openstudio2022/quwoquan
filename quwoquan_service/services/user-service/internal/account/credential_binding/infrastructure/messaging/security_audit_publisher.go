package messaging

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strconv"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	bindingapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	bindingmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	bindingports "quwoquan_service/services/user-service/internal/account/credential_binding/domain/ports"
)

const (
	CredentialAuditStream          = "events.user.credential_audit"
	CredentialAuditStreamRetention = 30 * 24 * time.Hour
)

type SecurityAuditPublisher struct {
	transport runtimemessaging.DurableRecordAppender
}

func NewSecurityAuditPublisher(
	transport runtimemessaging.DurableRecordAppender,
) (*SecurityAuditPublisher, error) {
	if transport == nil {
		return nil, errors.New("CredentialBinding durable audit transport is required")
	}
	return &SecurityAuditPublisher{transport: transport}, nil
}

func (publisher *SecurityAuditPublisher) PublishCredentialAudit(
	ctx context.Context,
	event bindingports.SecurityAuditEvent,
) error {
	if publisher == nil || publisher.transport == nil {
		return errors.New("CredentialBinding audit publisher is not configured")
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.AggregateID) == "" ||
		event.AggregateVersion <= 0 || event.OccurredAt.IsZero() {
		return errors.New("CredentialBinding audit event identity is invalid")
	}
	switch event.EventType {
	case bindingmodel.CredentialBoundEvent, bindingmodel.CredentialRevokedEvent:
	default:
		return fmt.Errorf("CredentialBinding audit event type %q is not canonical", event.EventType)
	}
	payload, err := canonicalAuditPayload(event.PayloadJSON, event.AggregateID)
	if err != nil {
		return err
	}
	if err := runtimemessaging.AppendDurableRecord(
		ctx,
		publisher.transport,
		CredentialAuditStream,
		map[string]string{
			"eventId":             event.EventID,
			"eventName":           event.EventType,
			"aggregateType":       "CredentialBinding",
			"credentialBindingId": event.AggregateID,
			"aggregateVersion":    strconv.FormatInt(event.AggregateVersion, 10),
			"payload":             string(payload),
			"occurredAt":          event.OccurredAt.UTC().Format(time.RFC3339Nano),
		},
		CredentialAuditStreamRetention,
	); err != nil {
		return fmt.Errorf("append CredentialBinding audit stream: %w", err)
	}
	return nil
}

func canonicalAuditPayload(raw []byte, aggregateID string) ([]byte, error) {
	var payload struct {
		ID string `json:"id"`
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		return nil, fmt.Errorf("decode CredentialBinding audit payload: %w", err)
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return nil, errors.New("CredentialBinding audit payload must contain one JSON object")
	}
	if strings.TrimSpace(payload.ID) == "" || payload.ID != aggregateID {
		return nil, errors.New("CredentialBinding audit payload identity mismatch")
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("encode CredentialBinding audit payload: %w", err)
	}
	return encoded, nil
}

var _ bindingapp.SecurityAuditPublisher = (*SecurityAuditPublisher)(nil)
