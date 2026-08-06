package persistence

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	reportmodel "quwoquan_service/services/content-service/internal/trust_safety/report/domain/model"
	reportports "quwoquan_service/services/content-service/internal/trust_safety/report/domain/ports"
)

const gatheringSafetyAuthorizationSelect = `
SELECT actor_persona_id, gathering_id, action, evidence_ref, decision_ref,
       decision_version, decision_digest, expires_at, issued_at, revoked_at
FROM report_gathering_safety_authorizations`

func (s *PGReportStore) IssueGatheringSafetyAuthorization(
	ctx context.Context,
	request reportports.IssueGatheringSafetyAuthorizationRequest,
) (reportports.GatheringSafetyAuthorization, bool, error) {
	request.ReportID = strings.TrimSpace(request.ReportID)
	request.ActorPersonaID = strings.TrimSpace(request.ActorPersonaID)
	request.IdempotencyKey = strings.TrimSpace(request.IdempotencyKey)
	request.ExpiresAt = request.ExpiresAt.UTC().Truncate(time.Microsecond)
	if request.ReportID == "" || request.ExpectedReportVersion < 1 ||
		request.ActorPersonaID == "" || request.IdempotencyKey == "" ||
		request.ExpiresAt.IsZero() {
		return reportports.GatheringSafetyAuthorization{}, false,
			reportports.ErrGatheringSafetyAuthorizationDenied
	}
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return reportports.GatheringSafetyAuthorization{}, false, err
	}
	defer tx.Rollback()

	var (
		version    int64
		targetType string
		targetID   string
		status     string
		resolution sql.NullString
	)
	err = tx.QueryRowContext(ctx, `
SELECT version, target_type, target_id, status, resolution
FROM reports
WHERE id=$1
FOR UPDATE`, request.ReportID).Scan(
		&version,
		&targetType,
		&targetID,
		&status,
		&resolution,
	)
	if err == sql.ErrNoRows {
		return reportports.GatheringSafetyAuthorization{}, false,
			reportports.ErrGatheringSafetyAuthorizationNotFound
	}
	if err != nil {
		return reportports.GatheringSafetyAuthorization{}, false, err
	}
	if version != request.ExpectedReportVersion {
		return reportports.GatheringSafetyAuthorization{}, false,
			reportports.ErrGatheringSafetyAuthorizationConflict
	}
	if targetType != string(reportmodel.TargetGathering) ||
		status != string(reportmodel.StatusResolved) ||
		resolution.String != string(reportmodel.ResolutionTerminateGathering) ||
		strings.TrimSpace(targetID) == "" {
		return reportports.GatheringSafetyAuthorization{}, false,
			reportports.ErrGatheringSafetyAuthorizationDenied
	}

	authorization, err := newGatheringSafetyAuthorization(
		request,
		strings.TrimSpace(targetID),
		version,
	)
	if err != nil {
		return reportports.GatheringSafetyAuthorization{}, false, err
	}
	existing, found, err := readGatheringSafetyAuthorizationForIssue(
		ctx,
		tx,
		request.ReportID,
		request.IdempotencyKey,
	)
	if err != nil {
		return reportports.GatheringSafetyAuthorization{}, false, err
	}
	if found {
		if !sameGatheringSafetyGrant(existing, authorization) {
			return reportports.GatheringSafetyAuthorization{}, false,
				reportports.ErrGatheringSafetyAuthorizationConflict
		}
		if err := tx.Commit(); err != nil {
			return reportports.GatheringSafetyAuthorization{}, false, err
		}
		return existing, true, nil
	}

	result, err := tx.ExecContext(ctx, `
INSERT INTO report_gathering_safety_authorizations (
  decision_ref, report_id, decision_version, decision_digest,
  actor_persona_id, gathering_id, action, evidence_ref,
  grant_idempotency_key, expires_at, issued_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
ON CONFLICT DO NOTHING`,
		authorization.DecisionRef,
		request.ReportID,
		authorization.DecisionVersion,
		authorization.DecisionDigest,
		authorization.ActorPersonaID,
		authorization.GatheringID,
		authorization.Action,
		authorization.EvidenceRef,
		request.IdempotencyKey,
		authorization.ExpiresAt,
		authorization.IssuedAt,
	)
	if err != nil {
		return reportports.GatheringSafetyAuthorization{}, false, err
	}
	inserted, err := result.RowsAffected()
	if err != nil {
		return reportports.GatheringSafetyAuthorization{}, false, err
	}
	if inserted != 1 {
		existing, found, readErr := readGatheringSafetyAuthorizationForIssue(
			ctx,
			tx,
			request.ReportID,
			request.IdempotencyKey,
		)
		if readErr != nil {
			return reportports.GatheringSafetyAuthorization{}, false, readErr
		}
		if !found || !sameGatheringSafetyGrant(existing, authorization) {
			return reportports.GatheringSafetyAuthorization{}, false,
				reportports.ErrGatheringSafetyAuthorizationConflict
		}
		authorization = existing
	}
	if err := tx.Commit(); err != nil {
		return reportports.GatheringSafetyAuthorization{}, false, err
	}
	return authorization, inserted != 1, nil
}

func (s *PGReportStore) RevokeGatheringSafetyAuthorization(
	ctx context.Context,
	request reportports.RevokeGatheringSafetyAuthorizationRequest,
) (reportports.GatheringSafetyAuthorization, bool, error) {
	request.ReportID = strings.TrimSpace(request.ReportID)
	request.DecisionRef = strings.TrimSpace(request.DecisionRef)
	request.IdempotencyKey = strings.TrimSpace(request.IdempotencyKey)
	request.RevokedAt = request.RevokedAt.UTC().Truncate(time.Microsecond)
	if request.ReportID == "" || request.DecisionRef == "" ||
		request.IdempotencyKey == "" || request.RevokedAt.IsZero() {
		return reportports.GatheringSafetyAuthorization{}, false,
			reportports.ErrGatheringSafetyAuthorizationDenied
	}
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return reportports.GatheringSafetyAuthorization{}, false, err
	}
	defer tx.Rollback()
	authorization, found, err := readGatheringSafetyAuthorization(
		ctx,
		tx.QueryRowContext(
			ctx,
			gatheringSafetyAuthorizationSelect+
				` WHERE report_id=$1 AND decision_ref=$2 FOR UPDATE`,
			request.ReportID,
			request.DecisionRef,
		),
	)
	if err != nil {
		return reportports.GatheringSafetyAuthorization{}, false, err
	}
	if !found {
		return reportports.GatheringSafetyAuthorization{}, false,
			reportports.ErrGatheringSafetyAuthorizationNotFound
	}
	if !authorization.RevokedAt.IsZero() {
		if err := tx.Commit(); err != nil {
			return reportports.GatheringSafetyAuthorization{}, false, err
		}
		return authorization, true, nil
	}
	result, err := tx.ExecContext(ctx, `
UPDATE report_gathering_safety_authorizations
SET revoked_at=$1, revoke_idempotency_key=$2
WHERE report_id=$3 AND decision_ref=$4 AND revoked_at IS NULL`,
		request.RevokedAt,
		request.IdempotencyKey,
		request.ReportID,
		request.DecisionRef,
	)
	if err != nil {
		return reportports.GatheringSafetyAuthorization{}, false,
			reportports.ErrGatheringSafetyAuthorizationConflict
	}
	updated, err := result.RowsAffected()
	if err != nil {
		return reportports.GatheringSafetyAuthorization{}, false, err
	}
	if updated != 1 {
		return reportports.GatheringSafetyAuthorization{}, false,
			reportports.ErrGatheringSafetyAuthorizationConflict
	}
	authorization.RevokedAt = request.RevokedAt
	if err := tx.Commit(); err != nil {
		return reportports.GatheringSafetyAuthorization{}, false, err
	}
	return authorization, false, nil
}

func (s *PGReportStore) ReadGatheringSafetyAuthorization(
	ctx context.Context,
	decisionRef string,
) (reportports.GatheringSafetyAuthorization, bool, error) {
	return readGatheringSafetyAuthorization(
		ctx,
		s.db.QueryRowContext(
			ctx,
			gatheringSafetyAuthorizationSelect+` WHERE decision_ref=$1`,
			strings.TrimSpace(decisionRef),
		),
	)
}

func readGatheringSafetyAuthorizationForIssue(
	ctx context.Context,
	tx *sql.Tx,
	reportID string,
	idempotencyKey string,
) (reportports.GatheringSafetyAuthorization, bool, error) {
	return readGatheringSafetyAuthorization(
		ctx,
		tx.QueryRowContext(
			ctx,
			gatheringSafetyAuthorizationSelect+
				` WHERE report_id=$1 OR grant_idempotency_key=$2
				  ORDER BY CASE WHEN grant_idempotency_key=$2 THEN 0 ELSE 1 END
				  LIMIT 1
				  FOR UPDATE`,
			reportID,
			idempotencyKey,
		),
	)
}

func readGatheringSafetyAuthorization(
	_ context.Context,
	row rowScanner,
) (reportports.GatheringSafetyAuthorization, bool, error) {
	var (
		value     reportports.GatheringSafetyAuthorization
		revokedAt sql.NullTime
	)
	err := row.Scan(
		&value.ActorPersonaID,
		&value.GatheringID,
		&value.Action,
		&value.EvidenceRef,
		&value.DecisionRef,
		&value.DecisionVersion,
		&value.DecisionDigest,
		&value.ExpiresAt,
		&value.IssuedAt,
		&revokedAt,
	)
	if err == sql.ErrNoRows {
		return reportports.GatheringSafetyAuthorization{}, false, nil
	}
	if err != nil {
		return reportports.GatheringSafetyAuthorization{}, false, err
	}
	value.ExpiresAt = value.ExpiresAt.UTC()
	value.IssuedAt = value.IssuedAt.UTC()
	if revokedAt.Valid {
		value.RevokedAt = revokedAt.Time.UTC()
	}
	return value, true, nil
}

func newGatheringSafetyAuthorization(
	request reportports.IssueGatheringSafetyAuthorizationRequest,
	gatheringID string,
	decisionVersion int64,
) (reportports.GatheringSafetyAuthorization, error) {
	evidenceRef := "content.report/" + request.ReportID
	decisionRef := evidenceRef + "@" + strconv.FormatInt(decisionVersion, 10) +
		"#" + reportports.GatheringSafetyActionTerminate
	issuedAt := time.Now().UTC().Truncate(time.Microsecond)
	digestPayload := struct {
		ActorPersonaID  string    `json:"actorPersonaId"`
		GatheringID     string    `json:"gatheringId"`
		Action          string    `json:"action"`
		EvidenceRef     string    `json:"evidenceRef"`
		DecisionRef     string    `json:"decisionRef"`
		DecisionVersion int64     `json:"decisionVersion"`
		ExpiresAt       time.Time `json:"expiresAt"`
	}{
		ActorPersonaID:  request.ActorPersonaID,
		GatheringID:     gatheringID,
		Action:          reportports.GatheringSafetyActionTerminate,
		EvidenceRef:     evidenceRef,
		DecisionRef:     decisionRef,
		DecisionVersion: decisionVersion,
		ExpiresAt:       request.ExpiresAt.UTC(),
	}
	encoded, err := json.Marshal(digestPayload)
	if err != nil {
		return reportports.GatheringSafetyAuthorization{}, fmt.Errorf(
			"encode Gathering safety decision digest: %w",
			err,
		)
	}
	digest := sha256.Sum256(encoded)
	return reportports.GatheringSafetyAuthorization{
		ActorPersonaID:  request.ActorPersonaID,
		GatheringID:     gatheringID,
		Action:          reportports.GatheringSafetyActionTerminate,
		EvidenceRef:     evidenceRef,
		DecisionRef:     decisionRef,
		DecisionVersion: decisionVersion,
		DecisionDigest:  hex.EncodeToString(digest[:]),
		ExpiresAt:       request.ExpiresAt.UTC(),
		IssuedAt:        issuedAt,
	}, nil
}

func sameGatheringSafetyGrant(
	left reportports.GatheringSafetyAuthorization,
	right reportports.GatheringSafetyAuthorization,
) bool {
	return left.ActorPersonaID == right.ActorPersonaID &&
		left.GatheringID == right.GatheringID &&
		left.Action == right.Action &&
		left.EvidenceRef == right.EvidenceRef &&
		left.DecisionRef == right.DecisionRef &&
		left.DecisionVersion == right.DecisionVersion &&
		left.DecisionDigest == right.DecisionDigest &&
		left.ExpiresAt.Equal(right.ExpiresAt)
}

var _ reportports.GatheringSafetyAuthorityStore = (*PGReportStore)(nil)
