package api_integration

import (
	"context"
	"fmt"
	"math"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/product-ops-service/internal/application"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/infrastructure/persistence"
)

func TestPostgresRtcMediaQoeSummaryUsesRawPercentileAndCanonicalDenominators(
	t *testing.T,
) {
	ctx := context.Background()
	schema := fmt.Sprintf("rtc_media_qoe_test_%d", time.Now().UnixNano())
	store, err := telemetrypersistence.NewPostgresTelemetryStore(controlPlanePGPool, schema)
	if err != nil {
		t.Fatalf("new postgres telemetry store: %v", err)
	}
	if err := store.EnsureSchema(ctx); err != nil {
		t.Fatalf("ensure postgres telemetry schema: %v", err)
	}
	t.Cleanup(func() {
		_, _ = controlPlanePGPool.Exec(
			context.Background(),
			`DROP SCHEMA "`+schema+`" CASCADE`,
		)
	})

	now := time.Now().UTC().Truncate(time.Hour).Add(30 * time.Minute)
	facade := application.NewRtcMediaQoeQueryFacadeWithClock(store, func() time.Time {
		return now
	})
	empty, err := facade.Get24HourSummary(ctx)
	if err != nil {
		t.Fatalf("get empty postgres rtc media QoE summary: %v", err)
	}
	if empty.HasSamples || empty.MediaConnectedRate != nil ||
		empty.ConnectP95MS != nil || empty.ConnectionLostRate != nil ||
		empty.GeneratedThrough != nil || empty.LagSeconds != nil {
		t.Fatalf("empty postgres summary must preserve null semantics: %+v", empty)
	}

	events := []application.EventRecordInput{
		postgresRtcMediaQoeEvent(now.Add(-10*time.Minute), "completed", true, 100, 1),
		postgresRtcMediaQoeEvent(now.Add(-5*time.Minute), "connection_lost", true, 200, 2),
		postgresRtcMediaQoeEvent(now.Add(-3*time.Minute), "abandoned", true, 9999, 99),
		postgresRtcMediaQoeEvent(now.Add(-time.Hour-10*time.Minute), "completed", true, 300, 3),
		postgresRtcMediaQoeEvent(now.Add(-time.Hour-5*time.Minute), "connect_failed", false, 0, 4),
	}
	telemetry := application.NewTelemetryService(store, store, store)
	if _, err := telemetry.ReportEventBatch(
		ctx,
		strings.Repeat("b", 64),
		events,
	); err != nil {
		t.Fatalf("report postgres rtc media QoE batch: %v", err)
	}

	got, err := facade.Get24HourSummary(ctx)
	if err != nil {
		t.Fatalf("get postgres rtc media QoE summary: %v", err)
	}
	if !got.HasSamples || got.EffectiveSampleCount != 4 ||
		got.MediaConnectedCount != 3 || got.ConnectionLostCount != 1 ||
		got.ReconnectCount != 10 || got.SourceKind != "raw_records" ||
		got.Freshness != "near_realtime" {
		t.Fatalf("unexpected postgres summary: %+v", got)
	}
	assertIntegrationFloatPointer(t, "mediaConnectedRate", got.MediaConnectedRate, 0.75)
	assertIntegrationFloatPointer(t, "connectP95Ms", got.ConnectP95MS, 290)
	assertIntegrationFloatPointer(t, "connectionLostRate", got.ConnectionLostRate, 1.0/3.0)
	if len(got.Series) != 24 {
		t.Fatalf("postgres summary must expose 24 UTC buckets, got %d", len(got.Series))
	}

	current := integrationRtcMediaQoePoint(t, got.Series, now.Truncate(time.Hour))
	previous := integrationRtcMediaQoePoint(
		t,
		got.Series,
		now.Truncate(time.Hour).Add(-time.Hour),
	)
	if !current.Partial || current.EffectiveSampleCount != 2 ||
		current.ConnectionLostCount != 1 {
		t.Fatalf("unexpected current postgres bucket: %+v", current)
	}
	if previous.Partial || previous.EffectiveSampleCount != 2 ||
		previous.MediaConnectedCount != 1 {
		t.Fatalf("unexpected previous postgres bucket: %+v", previous)
	}
	assertIntegrationFloatPointer(t, "current.connectP95Ms", current.ConnectP95MS, 195)
	assertIntegrationFloatPointer(t, "previous.connectP95Ms", previous.ConnectP95MS, 300)
}

func postgresRtcMediaQoeEvent(
	occurredAt time.Time,
	result string,
	mediaConnected bool,
	connectTimeMS int,
	reconnectCount int,
) application.EventRecordInput {
	callType := "video"
	participantCount := 2
	networkQuality := "good"
	event := application.EventRecordInput{
		LogType:            "event",
		EventType:          "rtc_media_qoe",
		SessionID:          "s.cXRjLW1lZGlhLXFvZQ." + fmt.Sprint(occurredAt.UnixMilli()),
		PageName:           "rtc_video",
		OccurredAt:         occurredAt.Format(time.RFC3339Nano),
		DeviceManufacturer: "Apple",
		DeviceModel:        "iPhone",
		AppVersion:         "1.0.0",
		NetworkClass:       "wifi",
		DevicePlatform:     "ios",
		CallType:           &callType,
		Result:             &result,
		ConnectTimeMS:      &connectTimeMS,
		MediaConnected:     &mediaConnected,
		ReconnectCount:     &reconnectCount,
		ParticipantCount:   &participantCount,
		NetworkQuality:     &networkQuality,
	}
	if result == "connection_lost" {
		disconnectReason := "unexpected_disconnect"
		event.DisconnectReason = &disconnectReason
	}
	return event
}

func integrationRtcMediaQoePoint(
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

func assertIntegrationFloatPointer(
	t *testing.T,
	name string,
	got *float64,
	want float64,
) {
	t.Helper()
	if got == nil || math.Abs(*got-want) > 1e-9 {
		t.Fatalf("%s=%v, want %.12f", name, got, want)
	}
}
