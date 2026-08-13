// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#open-005
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-003
package application_test

import (
	"context"
	"strings"
	"testing"
	"time"

	app "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
)

// GetParticipationStatus 是服务间最小 Participation 状态断言（INTERNAL）：
// 只回答「该 persona 在该 Gathering 的当前参与状态」，供 Content 在接受
// post.gatheringRef 回流引用前 fail-closed 校验。它不投影名单、申请答案或
// 私密事实；无参与时诚实返回空状态而不是伪造，也不因 viewer 缺失而拒绝
// （service principal 门在 HTTP 层执行）。

func TestGatheringParticipationStatusForActiveMember(t *testing.T) {
	now := time.Date(2026, 8, 6, 4, 0, 0, 0, time.UTC)
	value := gatheringQueryFixture(now)
	reader := &gatheringQueryReaderDouble{records: []app.GatheringReadModel{value}}
	facade := app.NewGatheringQueryFacade(reader, func() time.Time { return now })

	status, err := facade.GetParticipationStatus(
		context.Background(),
		app.ParticipationStatusQuery{
			GatheringID: value.ID,
			PersonaID:   "persona-member",
		},
	)
	if err != nil {
		t.Fatalf("GetParticipationStatus: %v", err)
	}
	if status.GatheringID != value.ID || status.PersonaID != "persona-member" {
		t.Fatalf("status identity mismatch: %+v", status)
	}
	if string(status.ParticipationState) != "active" {
		t.Fatalf("active member must project state active, got %q", status.ParticipationState)
	}
	if string(status.LifecycleStatus) != string(value.LifecycleStatus) {
		t.Fatalf(
			"lifecycle must mirror the aggregate, want %q got %q",
			value.LifecycleStatus,
			status.LifecycleStatus,
		)
	}
}

func TestGatheringParticipationStatusIsEmptyForOutsider(t *testing.T) {
	now := time.Date(2026, 8, 6, 4, 0, 0, 0, time.UTC)
	value := gatheringQueryFixture(now)
	reader := &gatheringQueryReaderDouble{records: []app.GatheringReadModel{value}}
	facade := app.NewGatheringQueryFacade(reader, func() time.Time { return now })

	status, err := facade.GetParticipationStatus(
		context.Background(),
		app.ParticipationStatusQuery{
			GatheringID: value.ID,
			PersonaID:   "persona-outsider-without-participation",
		},
	)
	if err != nil {
		t.Fatalf("GetParticipationStatus: %v", err)
	}
	if string(status.ParticipationState) != "" {
		t.Fatalf(
			"outsider must not be fabricated into a participant, got %q",
			status.ParticipationState,
		)
	}
}

func TestGatheringParticipationStatusRejectsBlankPersona(t *testing.T) {
	now := time.Date(2026, 8, 6, 4, 0, 0, 0, time.UTC)
	value := gatheringQueryFixture(now)
	reader := &gatheringQueryReaderDouble{records: []app.GatheringReadModel{value}}
	facade := app.NewGatheringQueryFacade(reader, func() time.Time { return now })

	if _, err := facade.GetParticipationStatus(
		context.Background(),
		app.ParticipationStatusQuery{GatheringID: value.ID, PersonaID: "   "},
	); err == nil {
		t.Fatal("blank personaId must be rejected")
	}
}

func TestGatheringParticipationStatusUnknownGatheringIsNotFound(t *testing.T) {
	now := time.Date(2026, 8, 6, 4, 0, 0, 0, time.UTC)
	reader := &gatheringQueryReaderDouble{}
	facade := app.NewGatheringQueryFacade(reader, func() time.Time { return now })

	_, err := facade.GetParticipationStatus(
		context.Background(),
		app.ParticipationStatusQuery{
			GatheringID: "gathering-missing",
			PersonaID:   "persona-member",
		},
	)
	if err == nil {
		t.Fatal("unknown gathering must be rejected")
	}
	if !strings.Contains(err.Error(), "CIRCLE.USER.gathering_not_found") {
		t.Fatalf("unknown gathering must map to gathering_not_found, got %v", err)
	}
}
