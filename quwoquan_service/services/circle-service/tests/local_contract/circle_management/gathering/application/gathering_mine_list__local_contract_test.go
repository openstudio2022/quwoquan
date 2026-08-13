// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#req-008
// Host 本人私有列表（ListMyHostedGatherings）：含 draft 与非公开 audiencePolicy、
// 只回受信 persona 名下、无 persona actor fail-closed（REQ-008 我的行动私有读面）。
package application_test

import (
	"context"
	"testing"
	"time"

	app "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
)

func TestListMyHostedGatheringsIncludesDraftAndNonPublicAudiences(t *testing.T) {
	now := time.Date(2026, 8, 6, 4, 0, 0, 0, time.UTC)
	published := gatheringQueryFixture(now)
	published.ID = "g-published"
	draft := gatheringQueryFixture(now)
	draft.ID = "g-draft"
	draft.LifecycleStatus = "draft"
	inviteOnly := gatheringQueryFixture(now)
	inviteOnly.ID = "g-invite-only"
	inviteOnly.PolicySet.AudiencePolicy = "invite_only"
	otherHost := gatheringQueryFixture(now)
	otherHost.ID = "g-other-host"
	otherHost.HostBinding.HostSubjectID = "someone-else"

	reader := &gatheringQueryReaderDouble{
		records: []app.GatheringReadModel{published, draft, inviteOnly, otherHost},
	}
	facade := app.NewGatheringQueryFacade(reader, func() time.Time { return now })

	page, err := facade.ListMyHostedGatherings(
		personaContext("host-subject"),
		app.ListMineQuery{Limit: 10},
	)
	if err != nil {
		t.Fatalf("ListMyHostedGatherings: %v", err)
	}
	got := map[string]bool{}
	for _, item := range page.Items {
		got[item.GatheringID] = true
	}
	if len(page.Items) != 3 || !got["g-published"] || !got["g-draft"] || !got["g-invite-only"] {
		t.Fatalf("mine list must include draft and non-public audiences, got %v", got)
	}
	if got["g-other-host"] {
		t.Fatalf("mine list leaked another host's gathering")
	}
	if page.HasMore {
		t.Fatalf("mine list must not report hasMore for a complete page")
	}
}

func TestListMyHostedGatheringsRequiresTrustedPersona(t *testing.T) {
	now := time.Date(2026, 8, 6, 4, 0, 0, 0, time.UTC)
	reader := &gatheringQueryReaderDouble{}
	facade := app.NewGatheringQueryFacade(reader, func() time.Time { return now })

	if _, err := facade.ListMyHostedGatherings(
		context.Background(),
		app.ListMineQuery{Limit: 10},
	); err == nil {
		t.Fatalf("mine list without a trusted persona actor must fail closed")
	}
}

func TestListMyHostedGatheringsPaginatesWithMineCursor(t *testing.T) {
	now := time.Date(2026, 8, 6, 4, 0, 0, 0, time.UTC)
	first := gatheringQueryFixture(now)
	first.ID = "g-mine-1"
	second := gatheringQueryFixture(now)
	second.ID = "g-mine-2"
	second.Schedule.StartAt = second.Schedule.StartAt.Add(24 * time.Hour)

	reader := &gatheringQueryReaderDouble{
		records: []app.GatheringReadModel{first, second},
	}
	facade := app.NewGatheringQueryFacade(reader, func() time.Time { return now })

	page1, err := facade.ListMyHostedGatherings(
		personaContext("host-subject"),
		app.ListMineQuery{Limit: 1},
	)
	if err != nil {
		t.Fatalf("mine page 1: %v", err)
	}
	if len(page1.Items) != 1 || !page1.HasMore || page1.NextCursor == "" {
		t.Fatalf("mine page 1 must expose keyset cursor, got items=%d hasMore=%v", len(page1.Items), page1.HasMore)
	}
	page2, err := facade.ListMyHostedGatherings(
		personaContext("host-subject"),
		app.ListMineQuery{Cursor: page1.NextCursor, Limit: 1},
	)
	if err != nil {
		t.Fatalf("mine page 2: %v", err)
	}
	if len(page2.Items) != 1 || page2.Items[0].GatheringID == page1.Items[0].GatheringID {
		t.Fatalf("mine page 2 must advance past page 1")
	}

	// host cursor 与 mine cursor 不得互换（kind 隔离）。
	if _, err := facade.ListMyHostedGatherings(
		personaContext("host-subject"),
		app.ListMineQuery{Cursor: "not-a-cursor", Limit: 1},
	); err == nil {
		t.Fatalf("invalid mine cursor must be rejected")
	}
}
