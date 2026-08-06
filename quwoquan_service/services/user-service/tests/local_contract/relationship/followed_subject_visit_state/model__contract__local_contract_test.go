// readiness_case: mark-followed-subject-visited-local
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
package local_contract

import (
	"errors"
	"testing"
	"time"

	visitmodel "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/domain/model"
)

// TestMarkVisitedCommandValidation 固定 metadata 业务规则：
// personaId/subjectType/subjectId/clientRequestId 必填，subjectType 闭集
// persona/circle/homepage/location（与 FollowSubjectKind 完全一致）。
func TestMarkVisitedCommandValidation(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 7, 19, 12, 0, 0, 0, time.UTC)

	if _, err := visitmodel.NewMarkVisitedCommand(
		"ps_1", "homepage", "home_1", now, "req-1",
	); err != nil {
		t.Fatalf("valid command must be accepted, got %v", err)
	}
	if _, err := visitmodel.NewMarkVisitedCommand(
		"ps_1", "persona", "ps_2", now, "req-2",
	); err != nil {
		t.Fatalf("canonical persona subject must be accepted, got %v", err)
	}
	if _, err := visitmodel.NewMarkVisitedCommand(
		"ps_1", "location", "location_shenzhen", now, "req-3",
	); err != nil {
		t.Fatalf("canonical location subject must be accepted, got %v", err)
	}

	invalid := []struct {
		name                                           string
		personaID, subjectType, subjectID, clientReqID string
	}{
		{"missing persona", "", "homepage", "home_1", "req-1"},
		{"missing subject", "ps_1", "homepage", "", "req-1"},
		{"missing clientRequestId", "ps_1", "homepage", "home_1", ""},
		{"invalid subjectType", "ps_1", "post", "post_1", "req-1"},
		{"retired user subjectType", "ps_1", "user", "ps_2", "req-1"},
	}
	for _, tc := range invalid {
		if _, err := visitmodel.NewMarkVisitedCommand(
			tc.personaID, tc.subjectType, tc.subjectID, now, tc.clientReqID,
		); !errors.Is(err, visitmodel.ErrInvalidCommand) {
			t.Fatalf("%s must be rejected, got %v", tc.name, err)
		}
	}
}

// TestMarkVisitedCommandNormalization 固定输入规范化：subjectType 大小写
// 不敏感、visitedAt 零值回退当前时间（水位仍由存储层 $max 单调保证）。
func TestMarkVisitedCommandNormalization(t *testing.T) {
	t.Parallel()
	command, err := visitmodel.NewMarkVisitedCommand(
		" ps_1 ", "HOMEPAGE", " home_1 ", time.Time{}, " req-1 ",
	)
	if err != nil {
		t.Fatalf("normalized command must be accepted, got %v", err)
	}
	if command.PersonaID != "ps_1" || command.SubjectType != "homepage" ||
		command.SubjectID != "home_1" || command.ClientRequestID != "req-1" {
		t.Fatalf("command not normalized: %+v", command)
	}
	if command.VisitedAt.IsZero() {
		t.Fatal("zero visitedAt must fall back to now")
	}
}
