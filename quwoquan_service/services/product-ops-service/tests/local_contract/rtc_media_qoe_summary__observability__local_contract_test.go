package local_contract

import (
	"context"
	"math"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	sls "github.com/aliyun/aliyun-log-go-sdk"

	"quwoquan_service/services/product-ops-service/internal/application"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/infrastructure/persistence"
)

func TestRtcMediaQoeSummaryUsesCanonicalDenominatorsAndUtcSeries(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	telemetry := application.NewTelemetryService(store, store, store)
	now := time.Now().UTC().Truncate(time.Hour).Add(30 * time.Minute)

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

func TestSLSEventLogStoreGetRtcMediaQoeSummaryQueriesRawSamples(t *testing.T) {
	now := time.Date(2026, time.July, 20, 19, 30, 0, 0, time.UTC)
	generatedThrough := now.Add(-20 * time.Second).Format(time.RFC3339Nano)
	client := &scriptedRtcMediaQoeSLSClient{responses: []*sls.GetLogsResponse{
		{Logs: []map[string]string{{
			"bucketEpoch":          strconv.FormatInt(now.Truncate(time.Hour).Unix(), 10),
			"effectiveSampleCount": "2",
			"mediaConnectedCount":  "2",
			"connectP95Ms":         "195",
			"connectionLostCount":  "1",
			"reconnectCount":       "3",
			"generatedThrough":     generatedThrough,
		}}},
		{Logs: []map[string]string{{
			"effectiveSampleCount": "4",
			"mediaConnectedCount":  "3",
			"connectP95Ms":         "290",
			"connectionLostCount":  "1",
			"reconnectCount":       "10",
			"generatedThrough":     generatedThrough,
		}}},
	}}
	store, err := telemetrypersistence.NewSLSEventLogStore(client, localSLSConfig())
	if err != nil {
		t.Fatalf("new SLS store: %v", err)
	}
	facade := application.NewRtcMediaQoeQueryFacadeWithClock(store, func() time.Time {
		return now
	})

	got, err := facade.Get24HourSummary(context.Background())
	if err != nil {
		t.Fatalf("get SLS rtc media QoE summary: %v", err)
	}
	if got.EffectiveSampleCount != 4 || got.MediaConnectedCount != 3 ||
		got.ConnectionLostCount != 1 || len(got.Series) != 24 {
		t.Fatalf("unexpected SLS summary: %+v", got)
	}
	assertFloatPointer(t, "sls.connectP95Ms", got.ConnectP95MS, 290)
	if got.GeneratedThrough == nil || *got.GeneratedThrough != generatedThrough ||
		got.LagSeconds == nil || *got.LagSeconds != 20 {
		t.Fatalf("unexpected SLS waterline: %+v", got)
	}

	requests := client.Requests()
	if len(requests) != 2 {
		t.Fatalf("SLS reader must issue overall and hourly raw queries, got %d", len(requests))
	}
	combined := requests[0].Query + "\n" + requests[1].Query
	for _, fragment := range []string{
		`eventType:"rtc_media_qoe"`,
		`result <> 'abandoned'`,
		`mediaConnected='true'`,
		`result='connection_lost'`,
		"approx_percentile",
		"from_iso8601_timestamp(occurredAt)",
		"date_trunc('hour'",
	} {
		if !strings.Contains(combined, fragment) {
			t.Fatalf("SLS raw query misses %q:\n%s", fragment, combined)
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

type scriptedRtcMediaQoeSLSClient struct {
	mu        sync.Mutex
	responses []*sls.GetLogsResponse
	requests  []*sls.GetLogRequest
}

func (*scriptedRtcMediaQoeSLSClient) PostLogStoreLogs(
	string,
	string,
	*sls.LogGroup,
	*string,
) error {
	return nil
}

func (c *scriptedRtcMediaQoeSLSClient) GetLogsV2(
	_ string,
	_ string,
	request *sls.GetLogRequest,
) (*sls.GetLogsResponse, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	requestCopy := *request
	c.requests = append(c.requests, &requestCopy)
	if len(c.responses) == 0 {
		return &sls.GetLogsResponse{}, nil
	}
	response := c.responses[0]
	c.responses = c.responses[1:]
	return response, nil
}

func (c *scriptedRtcMediaQoeSLSClient) Requests() []*sls.GetLogRequest {
	c.mu.Lock()
	defer c.mu.Unlock()
	out := make([]*sls.GetLogRequest, len(c.requests))
	for index, request := range c.requests {
		copy := *request
		out[index] = &copy
	}
	return out
}
