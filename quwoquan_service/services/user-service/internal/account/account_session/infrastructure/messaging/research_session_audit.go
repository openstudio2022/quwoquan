package messaging

import (
	"context"
	"errors"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	sessionapp "quwoquan_service/services/user-service/internal/account/account_session/application"
)

const (
	ResearchSessionAuditStream    = "events.user.research_identity_audit"
	researchSessionAuditRetention = 30 * 24 * time.Hour
)

type ResearchSessionAuditPublisher struct {
	transport runtimemessaging.DurableRecordAppender
}

func NewResearchSessionAuditPublisher(
	transport runtimemessaging.DurableRecordAppender,
) (*ResearchSessionAuditPublisher, error) {
	if transport == nil {
		return nil, errors.New("research identity durable audit transport is required")
	}
	return &ResearchSessionAuditPublisher{transport: transport}, nil
}

func (publisher *ResearchSessionAuditPublisher) AppendResearchSessionIssued(
	ctx context.Context,
	record sessionapp.ResearchSessionAuditRecord,
) error {
	if publisher == nil || publisher.transport == nil ||
		!strings.HasPrefix(record.SubjectHash, "sha256:") ||
		!strings.HasPrefix(record.AttestationIDHash, "sha256:") ||
		record.ExpiresAt.IsZero() {
		return errors.New("research identity audit record is invalid")
	}
	return runtimemessaging.AppendDurableRecord(
		ctx,
		publisher.transport,
		ResearchSessionAuditStream,
		map[string]string{
			"eventName":         "WhitelistedResearchSessionIssued",
			"subjectHash":       record.SubjectHash,
			"attestationIdHash": record.AttestationIDHash,
			"expiresAt":         record.ExpiresAt.UTC().Format(time.RFC3339Nano),
		},
		researchSessionAuditRetention,
	)
}

var _ sessionapp.ResearchSessionAuditAppender = (*ResearchSessionAuditPublisher)(nil)
