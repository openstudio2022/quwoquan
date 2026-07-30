package local_contract

import (
	"testing"
	"time"

	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
)

// structuredFacts 的准入条件是逐字段留证：信源政策为这些字段放开了官网与政府/文旅
// 门户，代价就是没有 factSource 的字段一律不投影。下面这批断言把「宁可缺字段也不
// 展示无来源事实」钉成契约。

func factSource(field homepagemodel.StructuredFactField) homepagemodel.FactSource {
	return homepagemodel.FactSource{
		Field:       field,
		SourceID:    "official_site:jiuzhaigou",
		SourceClass: homepagemodel.FactSourceOfficialSite,
		SourceURL:   "https://www.jiuzhai.com/opening",
		ObservedAt:  time.Date(2026, 7, 20, 1, 0, 0, 0, time.UTC),
		Confidence:  0.9,
	}
}

func intPtr(value int) *int { return &value }

func TestStructuredFactsDropFieldsWithoutFactSource(t *testing.T) {
	altitude := 2000
	facts, dropped := homepagemodel.SanitizeStructuredFacts(&homepagemodel.StructuredFacts{
		AltitudeMeters:  &altitude,
		OfficialWebsite: "https://www.jiuzhai.com",
		FactSources: []homepagemodel.FactSource{
			factSource(homepagemodel.FactFieldAltitudeMeters),
		},
	})
	if facts == nil {
		t.Fatalf("evidenced altitude must survive sanitization")
	}
	if facts.AltitudeMeters == nil || *facts.AltitudeMeters != 2000 {
		t.Fatalf("altitudeMeters must be kept, got %+v", facts.AltitudeMeters)
	}
	if facts.OfficialWebsite != "" {
		t.Fatalf("officialWebsite has no factSource and must be dropped, got %q", facts.OfficialWebsite)
	}
	if len(dropped) != 1 || dropped[0] != "officialWebsite: no factSource" {
		t.Fatalf("drop reason must name the field and cause, got %+v", dropped)
	}
	// 溯源只保留仍在投影里的字段，否则主页会带着指向空字段的证据条目。
	if len(facts.FactSources) != 1 || facts.FactSources[0].Field != homepagemodel.FactFieldAltitudeMeters {
		t.Fatalf("factSources must be pruned to surviving fields, got %+v", facts.FactSources)
	}
}

func TestStructuredFactsRejectSourceClassOutsidePolicy(t *testing.T) {
	source := factSource(homepagemodel.FactFieldTicketPriceRange)
	// OTA 不在 structuredFactsPolicy.allowedSourceClasses 内，即便形状完整也不构成证据。
	source.SourceClass = homepagemodel.StructuredFactSourceClass("ota")
	facts, dropped := homepagemodel.SanitizeStructuredFacts(&homepagemodel.StructuredFacts{
		TicketPriceRange: &homepagemodel.TicketPriceRange{
			Currency: "CNY", MinAmountCents: 16000, MaxAmountCents: 19000,
		},
		FactSources: []homepagemodel.FactSource{source},
	})
	if facts != nil {
		t.Fatalf("ticket price backed only by an out-of-policy source must not project, got %+v", facts)
	}
	if len(dropped) != 2 {
		t.Fatalf("expected both the rejected source and the unbacked field, got %+v", dropped)
	}
}

func TestStructuredFactsRejectNonHTTPSEvidenceAndWebsite(t *testing.T) {
	source := factSource(homepagemodel.FactFieldOfficialWebsite)
	source.SourceURL = "http://www.jiuzhai.com"
	facts, _ := homepagemodel.SanitizeStructuredFacts(&homepagemodel.StructuredFacts{
		OfficialWebsite: "https://www.jiuzhai.com",
		FactSources:     []homepagemodel.FactSource{source},
	})
	if facts != nil {
		t.Fatalf("plain-http evidence must not admit a fact, got %+v", facts)
	}

	facts, _ = homepagemodel.SanitizeStructuredFacts(&homepagemodel.StructuredFacts{
		OfficialWebsite: "www.jiuzhai.com",
		FactSources:     []homepagemodel.FactSource{factSource(homepagemodel.FactFieldOfficialWebsite)},
	})
	if facts != nil {
		t.Fatalf("scheme-less officialWebsite must be dropped, got %+v", facts)
	}
}

func TestStructuredFactsRejectIncoherentTicketPrice(t *testing.T) {
	cases := map[string]homepagemodel.TicketPriceRange{
		"free contradicts amount": {Currency: "CNY", MinAmountCents: 16000, MaxAmountCents: 16000, Free: true},
		"max below min":           {Currency: "CNY", MinAmountCents: 19000, MaxAmountCents: 16000},
		"currency not iso4217":    {Currency: "元", MinAmountCents: 0, MaxAmountCents: 100},
	}
	for name, price := range cases {
		t.Run(name, func(t *testing.T) {
			entry := price
			facts, dropped := homepagemodel.SanitizeStructuredFacts(&homepagemodel.StructuredFacts{
				TicketPriceRange: &entry,
				FactSources: []homepagemodel.FactSource{
					factSource(homepagemodel.FactFieldTicketPriceRange),
				},
			})
			if facts != nil {
				t.Fatalf("incoherent ticket price must be dropped, got %+v", facts)
			}
			if len(dropped) != 1 || dropped[0] != "ticketPriceRange: invalid range" {
				t.Fatalf("expected a single range rejection, got %+v", dropped)
			}
		})
	}
}

func TestStructuredFactsKeepCrossMidnightOpeningHoursAndDropBrokenEntries(t *testing.T) {
	facts, dropped := homepagemodel.SanitizeStructuredFacts(&homepagemodel.StructuredFacts{
		OpeningHours: []homepagemodel.OpeningHoursEntry{
			// 夜场跨零点：22:00 到次日 02:00 记为 1320-1560。
			{AppliesFrom: "07-01", AppliesTo: "08-31", Weekdays: []int{5, 6, 5}, OpenMinuteOfDay: 1320, CloseMinuteOfDay: 1560},
			{AppliesFrom: "11-01", Weekdays: []int{1}, OpenMinuteOfDay: 480, CloseMinuteOfDay: 1080},
			{Weekdays: []int{9}, OpenMinuteOfDay: 480, CloseMinuteOfDay: 1080},
			{OpenMinuteOfDay: 1080, CloseMinuteOfDay: 480},
			{AppliesFrom: "01-01", AppliesTo: "02-28", Closed: true, OpenMinuteOfDay: 999},
		},
		FactSources: []homepagemodel.FactSource{factSource(homepagemodel.FactFieldOpeningHours)},
	})
	if facts == nil {
		t.Fatalf("valid entries must survive alongside rejected ones")
	}
	if len(facts.OpeningHours) != 2 {
		t.Fatalf("expected the night session and the closed period, got %+v", facts.OpeningHours)
	}
	night := facts.OpeningHours[0]
	if night.CloseMinuteOfDay != 1560 {
		t.Fatalf("cross-midnight close must be preserved, got %d", night.CloseMinuteOfDay)
	}
	if len(night.Weekdays) != 2 || night.Weekdays[0] != 5 || night.Weekdays[1] != 6 {
		t.Fatalf("weekdays must be deduplicated and sorted, got %+v", night.Weekdays)
	}
	closedEntry := facts.OpeningHours[1]
	if closedEntry.OpenMinuteOfDay != 0 || closedEntry.CloseMinuteOfDay != 0 {
		t.Fatalf("closed entry must zero its time fields, got %+v", closedEntry)
	}
	// 半开适用期、越界星期、结束早于开始各报一条，共三条。
	if len(dropped) != 3 {
		t.Fatalf("expected three rejected entries, got %+v", dropped)
	}
}

func TestStructuredFactsKeepOnlySeasonAxisTagRefs(t *testing.T) {
	facts, _ := homepagemodel.SanitizeStructuredFacts(&homepagemodel.StructuredFacts{
		BestSeasonTagRefs: []string{
			"Topic/时间/四季/秋",
			"Topic/旅行/季节窗口/红叶季",
			"Topic/摄影/器材/全画幅",
			"秋天最美",
			"Topic/时间/四季/秋",
		},
		FactSources: []homepagemodel.FactSource{factSource(homepagemodel.FactFieldBestSeasonTagRefs)},
	})
	if facts == nil {
		t.Fatalf("season refs must survive")
	}
	if len(facts.BestSeasonTagRefs) != 2 {
		t.Fatalf("only season-axis refs may survive, got %+v", facts.BestSeasonTagRefs)
	}
	for _, ref := range facts.BestSeasonTagRefs {
		if ref == "Topic/摄影/器材/全画幅" || ref == "秋天最美" {
			t.Fatalf("off-axis or free-text ref leaked: %q", ref)
		}
	}
}

func TestStructuredFactsSurviveAggregateRoundTrip(t *testing.T) {
	now := time.Date(2026, 7, 20, 1, 0, 0, 0, time.UTC)
	aggregate, err := homepagemodel.Intake(homepagemodel.IntakeParams{
		Title:        "九寨沟",
		HomepageType: "sight",
		StructuredFacts: &homepagemodel.StructuredFacts{
			RecommendedDurationMinutes: &homepagemodel.DurationRange{MinMinutes: 240, MaxMinutes: 480},
			AltitudeMeters:             intPtr(2000),
			FactSources: []homepagemodel.FactSource{
				factSource(homepagemodel.FactFieldRecommendedDurationMinutes),
				factSource(homepagemodel.FactFieldAltitudeMeters),
			},
		},
		Now: now,
	})
	if err != nil {
		t.Fatalf("intake failed: %v", err)
	}
	snapshot := aggregate.Snapshot()
	if snapshot.StructuredFacts == nil || snapshot.StructuredFacts.AltitudeMeters == nil {
		t.Fatalf("structuredFacts must reach the persistence boundary, got %+v", snapshot.StructuredFacts)
	}
	restored, err := homepagemodel.Restore(snapshot)
	if err != nil {
		t.Fatalf("restore failed: %v", err)
	}
	view := restored.StructuredFactsView()
	if view == nil || len(view.FactSources) != 2 {
		t.Fatalf("restore must preserve provenance, got %+v", view)
	}
	// 聚合内部切片不得被调用方持有。
	view.FactSources[0].SourceID = "tampered"
	if again := restored.StructuredFactsView(); again.FactSources[0].SourceID == "tampered" {
		t.Fatalf("StructuredFactsView must return a deep copy")
	}
}

func TestRestoreReSanitizesLegacyDocumentsWithoutProvenance(t *testing.T) {
	now := time.Date(2026, 7, 20, 1, 0, 0, 0, time.UTC)
	// 存量文档可能早于留证要求写入，或被旁路直改过；读回时必须重新收敛。
	snapshot := homepagemodel.Snapshot{
		ID:                 "hp_legacy",
		Version:            3,
		Title:              "九寨沟",
		HomepageType:       "sight",
		CanonicalEntityID:  "entity:sight:jiuzhaigou",
		ObjectPageTemplate: "sight",
		Status:             homepagemodel.StatusPublished,
		CreatedAt:          now,
		UpdatedAt:          now,
		StructuredFacts: &homepagemodel.StructuredFacts{
			AltitudeMeters:  intPtr(2000),
			OfficialWebsite: "https://www.jiuzhai.com",
		},
	}
	restored, err := homepagemodel.Restore(snapshot)
	if err != nil {
		t.Fatalf("restore failed: %v", err)
	}
	if restored.StructuredFactsView() != nil {
		t.Fatalf("unevidenced legacy facts must not become visible on read, got %+v", restored.StructuredFactsView())
	}
	if len(restored.DroppedStructuredFactFields()) != 2 {
		t.Fatalf("both dropped fields must be diagnosable, got %+v", restored.DroppedStructuredFactFields())
	}
}
