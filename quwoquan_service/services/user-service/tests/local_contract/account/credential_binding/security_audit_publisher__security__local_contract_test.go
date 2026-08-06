package local_contract

import (
	"context"
	"strings"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	bindingmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	bindingports "quwoquan_service/services/user-service/internal/account/credential_binding/domain/ports"
	bindingmessaging "quwoquan_service/services/user-service/internal/account/credential_binding/infrastructure/messaging"
)

type credentialAuditTransport struct {
	message   runtimemessaging.DurableMessage
	stream    string
	retention time.Duration
}

func (transport *credentialAuditTransport) AppendDurable(
	_ context.Context,
	message runtimemessaging.DurableMessage,
) (string, error) {
	transport.message = message
	return "audit-record-1", nil
}

func (transport *credentialAuditTransport) SetDurableRetention(
	_ context.Context,
	stream string,
	retention time.Duration,
) error {
	transport.stream = stream
	transport.retention = retention
	return nil
}

func TestCredentialBindingAuditPublisherEmitsOnlyCanonicalRedactedFields(t *testing.T) {
	transport := &credentialAuditTransport{}
	publisher, err := bindingmessaging.NewSecurityAuditPublisher(transport)
	if err != nil {
		t.Fatal(err)
	}
	err = publisher.PublishCredentialAudit(t.Context(), bindingports.SecurityAuditEvent{
		EventID: "event-1", EventType: bindingmodel.CredentialBoundEvent,
		AggregateID: "binding-1", AggregateVersion: 1,
		PayloadJSON: []byte(`{"id":"binding-1"}`), OccurredAt: time.Now().UTC(),
	})
	if err != nil {
		t.Fatal(err)
	}
	fields := runtimemessaging.DurableFieldMap(transport.message.Fields)
	if transport.message.Stream != bindingmessaging.CredentialAuditStream ||
		transport.stream != bindingmessaging.CredentialAuditStream ||
		transport.retention != bindingmessaging.CredentialAuditStreamRetention {
		t.Fatalf("stream=%q retentionStream=%q retention=%s", transport.message.Stream, transport.stream, transport.retention)
	}
	if fields["eventId"] != "event-1" || fields["eventName"] != bindingmodel.CredentialBoundEvent ||
		fields["credentialBindingId"] != "binding-1" || fields["payload"] != `{"id":"binding-1"}` {
		t.Fatalf("audit fields=%v", fields)
	}
	for name, value := range fields {
		lower := strings.ToLower(name + "=" + value)
		if strings.Contains(lower, "credentialkey") || strings.Contains(lower, "token") ||
			strings.Contains(lower, "phone") || strings.Contains(lower, "provider") {
			t.Fatalf("secret-bearing audit field %q=%q", name, value)
		}
	}
}

func TestCredentialBindingAuditPublisherRejectsExpandedPayload(t *testing.T) {
	publisher, err := bindingmessaging.NewSecurityAuditPublisher(&credentialAuditTransport{})
	if err != nil {
		t.Fatal(err)
	}
	for name, payload := range map[string]string{
		"secret field":   `{"id":"binding-2","credentialKey":"secret"}`,
		"trailing value": `{"id":"binding-2"} {"id":"binding-2"}`,
	} {
		t.Run(name, func(t *testing.T) {
			err = publisher.PublishCredentialAudit(t.Context(), bindingports.SecurityAuditEvent{
				EventID: "event-2", EventType: bindingmodel.CredentialRevokedEvent,
				AggregateID: "binding-2", AggregateVersion: 2,
				PayloadJSON: []byte(payload), OccurredAt: time.Now().UTC(),
			})
			if err == nil {
				t.Fatal("non-canonical CredentialBinding audit payload was accepted")
			}
		})
	}
}
