package local_contract

import (
	"context"
	"math"
	"testing"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
)

func TestRtcMediaQoeSummaryUsesCanonicalDenominatorsAndUtcSeries(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	telemetry := application.NewTelemetryService(store, store)
	// ReportEventBatch 拒绝超过当前时钟五分钟的 future event。逻辑时钟固定在至少
	// 一个小时之前的第 30 分钟，既不会落入 future window，也让当前小时样本不跨桶。
	now := time.Now().UTC().Add(-90 * time.Minute).Truncate(time.Hour).Add(30 * time.Minute)

	events := []application.EventRecordInput{
		rtcMediaQoeEvent(now.Add(-10*time.Minute), "completed", true, 100, 1),
		rtcMediaQoeEvent(now.Add(-5*time.Minute), "connection_lost", true, 200, 2),
		rtcMediaQoeEvent(now.Add(-3*time.Minute), "abandoned", true, 9999, 99),
		rtcMediaQoeEvent(now.Add(-time.Hour-10*time.Minute), "completed", true, 300, 3),
		rtcMediaQoeEvent(now.Add(-time.Hour-5*time.Minute), "connect_failed", false, 0, 4),
	}
	if _, err := telemetry.ReportEventBatch(
		context.Background(),
		digestKey("rtc-media-qoe-summary"),
		events,
	); err != nil {
		t.Fatalf("report rtc media QoE: %v", err)
	}

	facade := application.NewRtcMediaQoeQueryFacadeWithClock(store, func() time.Time {
		return now
	})
	got, err := facade.Get24HourSummary(context.Background())
	if err != nil {
		t.Fatalf("get rtc media QoE summary: %v", err)
	}
	if !got.HasSamples || got.WindowHours != 24 ||
		got.EffectiveSampleCount != 4 || got.MediaConnectedCount != 3 ||
		got.ConnectionLostCount != 1 || got.ReconnectCount != 10 {
		t.Fatalf("unexpected summary counters: %+v", got)
	}
	assertFloatPointer(t, "mediaConnectedRate", got.MediaConnectedRate, 0.75)
	assertFloatPointer(t, "connectP95Ms", got.ConnectP95MS, 290)
	assertFloatPointer(t, "connectionLostRate", got.ConnectionLostRate, 1.0/3.0)
	if got.SourceKind != "raw_records" || got.Freshness != "near_realtime" ||
		got.GeneratedThrough == nil || got.LagSeconds == nil {
		t.Fatalf("unexpected source metadata: %+v", got)
	}
	if got.ActualFrom != now.Truncate(time.Hour).Add(-23*time.Hour).Format(time.RFC3339Nano) ||
		got.ActualTo != now.Format(time.RFC3339Nano) {
		t.Fatalf("unexpected actual window: from=%s to=%s", got.ActualFrom, got.ActualTo)
	}
	if len(got.Series) != 24 {
		t.Fatalf("UTC series must contain exactly 24 buckets, got %d", len(got.Series))
	}

	current := rtcMediaQoePoint(t, got.Series, now.Truncate(time.Hour))
	if !current.Partial || current.EffectiveSampleCount != 2 ||
		current.MediaConnectedCount != 2 || current.ConnectionLostCount != 1 ||
		current.ReconnectCount != 3 {
		t.Fatalf("unexpected current-hour point: %+v", current)
	}
	assertFloatPointer(t, "current.mediaConnectedRate", current.MediaConnectedRate, 1)
	assertFloatPointer(t, "current.connectP95Ms", current.ConnectP95MS, 195)
	assertFloatPointer(t, "current.connectionLostRate", current.ConnectionLostRate, 0.5)

	previous := rtcMediaQoePoint(t, got.Series, now.Truncate(time.Hour).Add(-time.Hour))
	if previous.Partial || previous.EffectiveSampleCount != 2 ||
		previous.MediaConnectedCount != 1 || previous.ConnectionLostCount != 0 ||
		previous.ReconnectCount != 7 {
		t.Fatalf("unexpected previous-hour point: %+v", previous)
	}
	assertFloatPointer(t, "previous.mediaConnectedRate", previous.MediaConnectedRate, 0.5)
	assertFloatPointer(t, "previous.connectP95Ms", previous.ConnectP95MS, 300)
	assertFloatPointer(t, "previous.connectionLostRate", previous.ConnectionLostRate, 0)
}

func TestRtcMediaQoeSummaryReturnsNullForEmptyDenominators(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	now := time.Now().UTC().Truncate(time.Hour).Add(15 * time.Minute)
	facade := application.NewRtcMediaQoeQueryFacadeWithClock(store, func() time.Time {
		return now
	})

	got, err := facade.Get24HourSummary(context.Background())
	if err != nil {
		t.Fatalf("get empty rtc media QoE summary: %v", err)
	}
	if got.HasSamples || got.EffectiveSampleCount != 0 ||
		got.MediaConnectedRate != nil || got.ConnectP95MS != nil ||
		got.ConnectionLostRate != nil || got.GeneratedThrough != nil ||
		got.LagSeconds != nil {
		t.Fatalf("empty summary must keep ratios, P95 and waterline null: %+v", got)
	}
	if len(got.Series) != 24 {
		t.Fatalf("empty summary must still expose 24 UTC buckets, got %d", len(got.Series))
	}
	for _, point := range got.Series {
		if point.MediaConnectedRate != nil || point.ConnectP95MS != nil ||
			point.ConnectionLostRate != nil || point.GeneratedThrough != nil {
			t.Fatalf("empty hourly bucket must not synthesize metrics: %+v", point)
		}
	}
}

func rtcMediaQoeEvent(
	occurredAt time.Time,
	result string,
	mediaConnected bool,
	connectTimeMS int,
	reconnectCount int,
) application.EventRecordInput {
	event := validEvent("rtc_media_qoe", "event", occurredAt)
	callType := "video"
	participantCount := 2
	networkQuality := "good"
	event.CallType = &callType
	event.Result = &result
	event.ConnectTimeMS = &connectTimeMS
	event.MediaConnected = &mediaConnected
	event.ReconnectCount = &reconnectCount
	event.ParticipantCount = &participantCount
	event.NetworkQuality = &networkQuality
	if result == "connection_lost" {
		disconnectReason := "unexpected_disconnect"
		event.DisconnectReason = &disconnectReason
	}
	return event
}

func rtcMediaQoePoint(
	t *testing.T,
	series []application.RtcMediaQoeHourlyPoint,
	bucketStart time.Time,
) application.RtcMediaQoeHourlyPoint {
	t.Helper()
	expected := bucketStart.UTC().Format(time.RFC3339Nano)
	for _, point := range series {
		if point.BucketStart == expected {
			return point
		}
	}
	t.Fatalf("missing UTC bucket %s", expected)
	return application.RtcMediaQoeHourlyPoint{}
}

func assertFloatPointer(t *testing.T, name string, got *float64, want float64) {
	t.Helper()
	if got == nil || math.Abs(*got-want) > 1e-9 {
		t.Fatalf("%s=%v, want %.12f", name, got, want)
	}
}
