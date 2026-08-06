package report

import (
	"context"
	"errors"
	"strings"
	"time"

	reporterrors "quwoquan_service/services/content-service/generated/trust_safety/report"
	reportports "quwoquan_service/services/content-service/internal/trust_safety/report/domain/ports"
)

const (
	GatheringSafetyActionTerminate = reportports.GatheringSafetyActionTerminate
	maxGatheringSafetyGrantTTL     = 5 * time.Minute
	maxGatheringSafetyReportID     = 36
	maxGatheringSafetyActorID      = 64
	maxGatheringSafetyReference    = 192
	maxGatheringSafetyIdempotency  = 128
)

func (s *ReportService) GrantGatheringSafetyTermination(
	ctx context.Context,
	command GrantGatheringSafetyTerminationCommand,
) (GatheringSafetyTerminationGrantResult, error) {
	if s == nil || s.data.Safety == nil {
		return GatheringSafetyTerminationGrantResult{},
			reporterrors.AppErrorFromGatheringSafetyAuthorityUnavailable(
				"Gathering safety authority is unavailable",
			)
	}
	now := s.now().UTC()
	command.ReportID = strings.TrimSpace(command.ReportID)
	command.ActorPersonaID = strings.TrimSpace(command.ActorPersonaID)
	command.IdempotencyKey = strings.TrimSpace(command.IdempotencyKey)
	command.ExpiresAt = command.ExpiresAt.UTC()
	if command.ReportID == "" ||
		len(command.ReportID) > maxGatheringSafetyReportID ||
		command.ExpectedReportVersion < 1 ||
		command.ActorPersonaID == "" ||
		len(command.ActorPersonaID) > maxGatheringSafetyActorID ||
		command.IdempotencyKey == "" ||
		len(command.IdempotencyKey) > maxGatheringSafetyIdempotency ||
		!command.ExpiresAt.After(now) ||
		command.ExpiresAt.After(now.Add(maxGatheringSafetyGrantTTL)) {
		return GatheringSafetyTerminationGrantResult{},
			reporterrors.AppErrorFromGatheringSafetyAuthorizationInvalid(
				"Gathering safety grant request is invalid",
			)
	}
	authorization, replayed, err := s.data.Safety.IssueGatheringSafetyAuthorization(
		ctx,
		reportports.IssueGatheringSafetyAuthorizationRequest{
			ReportID:              command.ReportID,
			ExpectedReportVersion: command.ExpectedReportVersion,
			ActorPersonaID:        command.ActorPersonaID,
			ExpiresAt:             command.ExpiresAt,
			IdempotencyKey:        command.IdempotencyKey,
		},
	)
	if err != nil {
		return GatheringSafetyTerminationGrantResult{}, mapGatheringSafetyAuthorityError(err)
	}
	return gatheringSafetyGrantResult(authorization, replayed), nil
}

func (s *ReportService) RevokeGatheringSafetyTermination(
	ctx context.Context,
	command RevokeGatheringSafetyTerminationCommand,
) (GatheringSafetyTerminationGrantResult, error) {
	if s == nil || s.data.Safety == nil {
		return GatheringSafetyTerminationGrantResult{},
			reporterrors.AppErrorFromGatheringSafetyAuthorityUnavailable(
				"Gathering safety authority is unavailable",
			)
	}
	command.ReportID = strings.TrimSpace(command.ReportID)
	command.DecisionRef = strings.TrimSpace(command.DecisionRef)
	command.IdempotencyKey = strings.TrimSpace(command.IdempotencyKey)
	if command.ReportID == "" ||
		len(command.ReportID) > maxGatheringSafetyReportID ||
		command.DecisionRef == "" ||
		len(command.DecisionRef) > maxGatheringSafetyReference ||
		command.IdempotencyKey == "" ||
		len(command.IdempotencyKey) > maxGatheringSafetyIdempotency {
		return GatheringSafetyTerminationGrantResult{},
			reporterrors.AppErrorFromGatheringSafetyAuthorizationInvalid(
				"Gathering safety revoke request is invalid",
			)
	}
	authorization, replayed, err := s.data.Safety.RevokeGatheringSafetyAuthorization(
		ctx,
		reportports.RevokeGatheringSafetyAuthorizationRequest{
			ReportID:       command.ReportID,
			DecisionRef:    command.DecisionRef,
			IdempotencyKey: command.IdempotencyKey,
			RevokedAt:      s.now().UTC(),
		},
	)
	if err != nil {
		return GatheringSafetyTerminationGrantResult{}, mapGatheringSafetyAuthorityError(err)
	}
	return gatheringSafetyGrantResult(authorization, replayed), nil
}

func (s *ReportService) AuthorizeGatheringSafetyTermination(
	ctx context.Context,
	query AuthorizeGatheringSafetyTerminationQuery,
) (GatheringSafetyTerminationAuthoritySlice, error) {
	if s == nil || s.data.Safety == nil {
		return GatheringSafetyTerminationAuthoritySlice{},
			reporterrors.AppErrorFromGatheringSafetyAuthorityUnavailable(
				"Gathering safety authority is unavailable",
			)
	}
	query.ActorPersonaID = strings.TrimSpace(query.ActorPersonaID)
	query.GatheringID = strings.TrimSpace(query.GatheringID)
	query.Action = strings.TrimSpace(query.Action)
	query.EvidenceRef = strings.TrimSpace(query.EvidenceRef)
	query.DecisionRef = strings.TrimSpace(query.DecisionRef)
	if query.ActorPersonaID == "" ||
		len(query.ActorPersonaID) > maxGatheringSafetyActorID ||
		query.GatheringID == "" ||
		len(query.GatheringID) > maxGatheringSafetyActorID ||
		query.Action != GatheringSafetyActionTerminate ||
		query.EvidenceRef == "" ||
		len(query.EvidenceRef) > maxGatheringSafetyReference ||
		query.DecisionRef == "" ||
		len(query.DecisionRef) > maxGatheringSafetyReference {
		return GatheringSafetyTerminationAuthoritySlice{},
			reporterrors.AppErrorFromGatheringSafetyAuthorizationInvalid(
				"Gathering safety authorization request is invalid",
			)
	}
	authorization, found, err := s.data.Safety.ReadGatheringSafetyAuthorization(
		ctx,
		query.DecisionRef,
	)
	if err != nil {
		return GatheringSafetyTerminationAuthoritySlice{},
			reporterrors.AppErrorFromGatheringSafetyAuthorityUnavailable(
				"Gathering safety authority read failed",
			)
	}
	now := s.now().UTC()
	if !found ||
		authorization.ActorPersonaID != query.ActorPersonaID ||
		authorization.GatheringID != query.GatheringID ||
		authorization.Action != query.Action ||
		authorization.EvidenceRef != query.EvidenceRef ||
		authorization.DecisionRef != query.DecisionRef ||
		authorization.DecisionVersion < 1 ||
		strings.TrimSpace(authorization.DecisionDigest) == "" ||
		authorization.ExpiresAt.IsZero() ||
		!now.Before(authorization.ExpiresAt) ||
		!authorization.RevokedAt.IsZero() {
		return GatheringSafetyTerminationAuthoritySlice{Allowed: false}, nil
	}
	expiresAt := authorization.ExpiresAt.UTC()
	return GatheringSafetyTerminationAuthoritySlice{
		Allowed:         true,
		ActorPersonaID:  authorization.ActorPersonaID,
		GatheringID:     authorization.GatheringID,
		Action:          authorization.Action,
		EvidenceRef:     authorization.EvidenceRef,
		DecisionRef:     authorization.DecisionRef,
		DecisionVersion: authorization.DecisionVersion,
		DecisionDigest:  authorization.DecisionDigest,
		ExpiresAt:       &expiresAt,
	}, nil
}

func gatheringSafetyGrantResult(
	value reportports.GatheringSafetyAuthorization,
	replayed bool,
) GatheringSafetyTerminationGrantResult {
	result := GatheringSafetyTerminationGrantResult{
		ActorPersonaID:  value.ActorPersonaID,
		GatheringID:     value.GatheringID,
		Action:          value.Action,
		EvidenceRef:     value.EvidenceRef,
		DecisionRef:     value.DecisionRef,
		DecisionVersion: value.DecisionVersion,
		DecisionDigest:  value.DecisionDigest,
		ExpiresAt:       value.ExpiresAt.UTC(),
		Replayed:        replayed,
	}
	if !value.RevokedAt.IsZero() {
		revokedAt := value.RevokedAt.UTC()
		result.RevokedAt = &revokedAt
	}
	return result
}

func mapGatheringSafetyAuthorityError(err error) error {
	switch {
	case errors.Is(err, reportports.ErrGatheringSafetyAuthorizationNotFound):
		return reporterrors.AppErrorFromReportNotFound(
			"Gathering safety authorization report was not found",
		)
	case errors.Is(err, reportports.ErrGatheringSafetyAuthorizationDenied):
		return reporterrors.AppErrorFromGatheringSafetyAuthorizationDenied(
			"Gathering safety authorization denied",
		)
	case errors.Is(err, reportports.ErrGatheringSafetyAuthorizationConflict):
		return reporterrors.AppErrorFromGatheringSafetyAuthorizationConflict(
			"Gathering safety authorization conflict",
		)
	default:
		return reporterrors.AppErrorFromGatheringSafetyAuthorityUnavailable(
			"Gathering safety authority persistence failed",
		)
	}
}
