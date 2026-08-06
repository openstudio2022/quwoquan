package runtimemessaging

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	dto "github.com/prometheus/client_model/go"

	rtredis "quwoquan_service/runtime/redis"
)

type testRedisScenes map[string]rtredis.Client

func (scenes testRedisScenes) LookupScene(name string) (rtredis.Client, bool) {
	client, ok := scenes[name]
	return client, ok
}

type unavailableRedisClient struct {
	rtredis.Client
}

func (unavailableRedisClient) Ping(context.Context) error {
	return errors.New("unavailable")
}

func TestRequireRedisMessageTransportReturnsOnlyDeclaredHealthyScenes(t *testing.T) {
	t.Parallel()

	general := rtredis.NewMemoryClient()
	realtime := rtredis.NewMemoryClient()
	transport, err := RequireRedisMessageTransport(
		context.Background(),
		MessageTransportBinding{
			State:               "enabled",
			AdapterID:           RedisMessageTransportAdapter,
			TimeoutMilliseconds: 100,
		},
		MessageTransportRoot{
			RootID:              "chat-service-api",
			RequiredRedisScenes: []string{"general", "realtime"},
		},
		testRedisScenes{"general": general, "realtime": realtime, "other": rtredis.NewMemoryClient()},
	)
	if err != nil {
		t.Fatalf("RequireRedisMessageTransport() error = %v", err)
	}
	if transport.RootID() != "chat-service-api" {
		t.Fatalf("RootID() = %q", transport.RootID())
	}
	if client, ok := transport.Scene("general"); !ok || client != general {
		t.Fatal("general scene was not resolved")
	}
	if _, ok := transport.Scene("other"); ok {
		t.Fatal("undeclared Redis scene must not be exposed")
	}
}

func TestRequireRedisMessageTransportFailsClosed(t *testing.T) {
	t.Parallel()

	root := MessageTransportRoot{RootID: "chat-service-api", RequiredRedisScenes: []string{"general"}}
	scenes := testRedisScenes{"general": rtredis.NewMemoryClient()}
	tests := []struct {
		name    string
		binding MessageTransportBinding
		scenes  RedisSceneProvider
	}{
		{
			name:    "blocked binding",
			binding: MessageTransportBinding{State: "blocked", AdapterID: RedisMessageTransportAdapter, TimeoutMilliseconds: 100},
			scenes:  scenes,
		},
		{
			name:    "unexpected adapter",
			binding: MessageTransportBinding{State: "enabled", AdapterID: "infra.message.nats", TimeoutMilliseconds: 100},
			scenes:  scenes,
		},
		{
			name:    "unhealthy scene",
			binding: MessageTransportBinding{State: "enabled", AdapterID: RedisMessageTransportAdapter, TimeoutMilliseconds: 100},
			scenes:  testRedisScenes{"general": unavailableRedisClient{}},
		},
	}
	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			if _, err := RequireRedisMessageTransport(context.Background(), test.binding, root, test.scenes); err == nil {
				t.Fatal("RequireRedisMessageTransport() error = nil, want fail-closed error")
			}
		})
	}
}

func TestRequireConfiguredRedisMessageTransportOnlyPermitsMemoryFixtureInAlpha(t *testing.T) {
	t.Parallel()

	router := rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {Mode: "memory"},
		},
		DefaultScene: "general",
	})
	t.Cleanup(func() { _ = router.Close() })
	root := MessageTransportRoot{
		RootID:              "chat-service-api",
		RequiredRedisScenes: []string{"general"},
	}

	if _, err := RequireConfiguredRedisMessageTransport(
		context.Background(),
		"alpha",
		true,
		MessageTransportBinding{
			State:               "enabled",
			AdapterID:           RedisMessageTransportFixture,
			TimeoutMilliseconds: 100,
		},
		root,
		router,
		map[string]string{"general": "memory"},
	); err != nil {
		t.Fatalf("alpha fixture preflight error = %v", err)
	}
	if _, err := RequireConfiguredRedisMessageTransport(
		context.Background(),
		"gamma",
		true,
		MessageTransportBinding{
			State:               "enabled",
			AdapterID:           RedisMessageTransportAdapter,
			TimeoutMilliseconds: 100,
		},
		root,
		router,
		map[string]string{"general": "memory"},
	); err == nil {
		t.Fatal("gamma memory Redis unexpectedly passed message transport preflight")
	}
	if _, err := RequireConfiguredRedisMessageTransport(
		context.Background(),
		"gamma",
		true,
		MessageTransportBinding{
			State:               "enabled",
			AdapterID:           RedisMessageTransportFixture,
			TimeoutMilliseconds: 100,
		},
		root,
		router,
		map[string]string{"general": "standalone"},
	); err == nil {
		t.Fatal("gamma fixture binding unexpectedly passed message transport preflight")
	}
}

func TestMessageTransportLatencySamplesAreHistogramsNotP95Gauges(t *testing.T) {
	const rootID = "provider-evidence-metric-contract"
	transport := &RedisMessageTransport{
		rootID:  rootID,
		adapter: RedisMessageTransportAdapter,
	}
	transport.recordOperation(
		"durable_append",
		time.Now().Add(-25*time.Millisecond),
		nil,
	)
	transport.recordOperation(
		"durable_consume",
		time.Now().Add(-40*time.Millisecond),
		nil,
	)

	families, err := prometheus.DefaultGatherer.Gather()
	if err != nil {
		t.Fatalf("Gather() error = %v", err)
	}
	byName := make(map[string]*dto.MetricFamily, len(families))
	for _, family := range families {
		byName[family.GetName()] = family
	}
	for _, metricName := range []string{
		"qwq_message_transport_publish_p95",
		"qwq_message_transport_consume_p95",
	} {
		if _, exists := byName[metricName]; exists {
			t.Fatalf("%s must be a recording rule, not a runtime Gauge", metricName)
		}
	}
	for metricName, operation := range map[string]string{
		"qwq_message_transport_publish_duration_seconds": "durable_append",
		"qwq_message_transport_consume_duration_seconds": "durable_consume",
	} {
		family := byName[metricName]
		if family == nil {
			t.Fatalf("%s was not gathered", metricName)
		}
		if family.GetType() != dto.MetricType_HISTOGRAM {
			t.Fatalf("%s type = %s, want HISTOGRAM", metricName, family.GetType())
		}
		metric := metricWithLabels(family, map[string]string{
			"root":      rootID,
			"adapter":   RedisMessageTransportAdapter,
			"operation": operation,
		})
		if metric == nil || metric.GetHistogram().GetSampleCount() != 1 {
			t.Fatalf("%s did not retain the latency sample: %+v", metricName, metric)
		}
		if metric.GetHistogram().GetSampleSum() <= 0 {
			t.Fatalf("%s sample sum must be positive", metricName)
		}
	}
}

func TestRedisMessageTransportSeparatesEphemeralAndDurableDelivery(t *testing.T) {
	t.Parallel()

	realtime := rtredis.NewMemoryClient()
	durable := rtredis.NewMemoryClient()
	transport, err := NewRedisMessageTransport(realtime, durable)
	if err != nil {
		t.Fatalf("NewRedisMessageTransport() error = %v", err)
	}
	subscription, err := transport.SubscribeEphemeral(context.Background(), "chat.user-1")
	if err != nil {
		t.Fatalf("SubscribeEphemeral() error = %v", err)
	}
	t.Cleanup(func() { _ = subscription.Close() })
	if err := transport.PublishEphemeral(
		context.Background(),
		EphemeralMessage{Channel: "chat.user-1", Payload: []byte(`{"kind":"hint"}`)},
	); err != nil {
		t.Fatalf("PublishEphemeral() error = %v", err)
	}
	select {
	case received := <-subscription.Channel():
		if string(received.Payload) != `{"kind":"hint"}` {
			t.Fatalf("ephemeral payload = %q", received.Payload)
		}
	case <-time.After(time.Second):
		t.Fatal("ephemeral publish was not delivered")
	}
	if _, err := transport.AppendDurable(
		context.Background(),
		DurableMessage{
			Stream: "events.chat.assistant_mentions",
			Fields: []DurableField{{Name: "conversationId", Value: "c-1"}},
		},
	); err != nil {
		t.Fatalf("AppendDurable() error = %v", err)
	}
	if err := durable.XGroupCreateMkStream(
		context.Background(),
		"events.chat.assistant_mentions",
		"assistant",
		"0",
	); err != nil {
		t.Fatalf("XGroupCreateMkStream() error = %v", err)
	}
	messages, err := transport.ReadDurable(
		context.Background(),
		StreamReadRequest{
			Stream:   "events.chat.assistant_mentions",
			Group:    "assistant",
			Consumer: "worker-1",
			Count:    1,
			Block:    time.Second,
		},
	)
	if err != nil {
		t.Fatalf("ReadDurable() error = %v", err)
	}
	if len(messages) != 1 || durableFieldValue(messages[0].Fields, "conversationId") != "c-1" {
		t.Fatalf("durable stream delivery = %+v", messages)
	}
	reclaimed, _, err := transport.ReclaimDurable(
		context.Background(),
		"events.chat.assistant_mentions",
		"assistant",
		"recovery-worker",
		0,
		"0-0",
		1,
	)
	if err != nil {
		t.Fatalf("ReclaimDurable() error = %v", err)
	}
	if len(reclaimed) != 1 || reclaimed[0].ID != messages[0].ID {
		t.Fatalf("reclaimed delivery = %+v, want original %q", reclaimed, messages[0].ID)
	}
	if err := transport.AckDurable(
		context.Background(),
		"events.chat.assistant_mentions",
		"assistant",
		messages[0].ID,
	); err != nil {
		t.Fatalf("AckDurable() error = %v", err)
	}
	if _, err := transport.PublishDeadLetter(
		context.Background(),
		DeadLetterMessage{
			SourceStream:      "events.chat.assistant_mentions",
			DestinationStream: "events.chat.assistant_mentions.dlq",
			SourceID:          messages[0].ID,
			Reason:            "decode_failed",
			Fields:            messages[0].Fields,
		},
	); err != nil {
		t.Fatalf("PublishDeadLetter() error = %v", err)
	}
	if err := durable.XGroupCreateMkStream(
		context.Background(),
		"events.chat.assistant_mentions.dlq",
		"ops",
		"0",
	); err != nil {
		t.Fatalf("create DLQ group: %v", err)
	}
	deadLetters, err := transport.ReadDurable(
		context.Background(),
		StreamReadRequest{
			Stream:   "events.chat.assistant_mentions.dlq",
			Group:    "ops",
			Consumer: "ops-1",
			Count:    1,
			Block:    time.Second,
		},
	)
	if err != nil {
		t.Fatalf("read DLQ: %v", err)
	}
	if len(deadLetters) != 1 || durableFieldValue(deadLetters[0].Fields, "reason") != "decode_failed" {
		t.Fatalf("dead-letter delivery = %+v", deadLetters)
	}
}

func TestRedisMessageTransportRetentionTrimsActiveStreamByAge(t *testing.T) {
	ctx := context.Background()
	durable := rtredis.NewMemoryClient()
	transport, err := NewRedisMessageTransport(
		rtredis.NewMemoryClient(),
		durable,
	)
	if err != nil {
		t.Fatalf("NewRedisMessageTransport() error = %v", err)
	}
	const stream = "events.search.recommendation_signals"
	if _, err := transport.AppendDurable(ctx, DurableMessage{
		Stream: stream,
		Fields: []DurableField{
			{Name: "signalId", Value: "old"},
		},
	}); err != nil {
		t.Fatalf("append old message: %v", err)
	}
	time.Sleep(20 * time.Millisecond)
	if _, err := transport.AppendDurable(ctx, DurableMessage{
		Stream: stream,
		Fields: []DurableField{
			{Name: "signalId", Value: "recent"},
		},
	}); err != nil {
		t.Fatalf("append recent message: %v", err)
	}
	if err := transport.SetDurableRetention(
		ctx,
		stream,
		10*time.Millisecond,
	); err != nil {
		t.Fatalf("SetDurableRetention() error = %v", err)
	}
	if err := durable.XGroupCreateMkStream(
		ctx,
		stream,
		"audit",
		"0",
	); err != nil {
		t.Fatalf("create audit group: %v", err)
	}
	messages, err := transport.ReadDurable(ctx, StreamReadRequest{
		Stream:   stream,
		Group:    "audit",
		Consumer: "audit-1",
		Count:    10,
		Block:    20 * time.Millisecond,
	})
	if err != nil {
		t.Fatalf("ReadDurable() error = %v", err)
	}
	if len(messages) != 1 ||
		durableFieldValue(messages[0].Fields, "signalId") != "recent" {
		t.Fatalf(
			"retained messages = %+v, want only recent signal",
			messages,
		)
	}
}

func durableFieldValue(fields []DurableField, name string) string {
	for _, field := range fields {
		if field.Name == name {
			return field.Value
		}
	}
	return ""
}

func metricWithLabels(
	family *dto.MetricFamily,
	expected map[string]string,
) *dto.Metric {
	for _, metric := range family.GetMetric() {
		labels := make(map[string]string, len(metric.GetLabel()))
		for _, label := range metric.GetLabel() {
			labels[label.GetName()] = label.GetValue()
		}
		matches := true
		for name, value := range expected {
			if labels[name] != value {
				matches = false
				break
			}
		}
		if matches {
			return metric
		}
	}
	return nil
}
