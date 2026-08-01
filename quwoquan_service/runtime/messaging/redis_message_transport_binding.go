package runtimemessaging

import (
	"context"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	rtredis "quwoquan_service/runtime/redis"
)

const (
	RuntimeMessageTransportCapability = "runtime.message.transport"
	RedisMessageTransportAdapter      = "infra.redis.message_transport"
	RedisMessageTransportFixture      = "infra.redis.message_transport_fixture"
)

const realtimeChatResumeStreamPrefix = "rt:resume:chat:user:"

// RealtimeChatResumeStream returns the stream coordinate declared by the
// shared Redis keyspace contract. Callers must supply only a trusted account
// identity; HTTP input must never select an arbitrary stream.
func RealtimeChatResumeStream(accountID string) string {
	return realtimeChatResumeStreamPrefix + strings.TrimSpace(accountID)
}

// IsCanonicalStreamCursor rejects provider aliases such as "$" or ">" at
// the public HTTP boundary. Only an immutable Redis stream coordinate can be
// persisted and replayed safely by a client device.
func IsCanonicalStreamCursor(value string) bool {
	parts := strings.Split(strings.TrimSpace(value), "-")
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		return false
	}
	for _, part := range parts {
		if _, err := strconv.ParseUint(part, 10, 64); err != nil {
			return false
		}
	}
	return true
}

var (
	messageTransportOperations = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Namespace: "qwq_message_transport",
			Name:      "operations_total",
			Help:      "Message transport operations by root, adapter, delivery mode and result.",
		},
		[]string{"root", "adapter", "operation", "status"},
	)
	messageTransportLatency = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Namespace: "qwq_message_transport",
			Name:      "operation_duration_seconds",
			Help:      "Message transport operation latency by root and delivery mode.",
			Buckets:   prometheus.DefBuckets,
		},
		[]string{"root", "adapter", "operation"},
	)
	messageTransportPending = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Namespace: "qwq_message_transport",
			Name:      "stream_pending",
			Help:      "Pending durable records by root, stream and consumer group.",
		},
		[]string{"root", "adapter", "stream", "group"},
	)
	messageTransportDeadLetters = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Namespace: "qwq_message_transport",
			Name:      "dead_letters_total",
			Help:      "Durable records written to a dead-letter stream by root and reason.",
		},
		[]string{"root", "adapter", "stream", "reason"},
	)
	messageTransportPreflight = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Namespace: "qwq_message_transport",
			Name:      "preflight_ready",
			Help:      "Message transport preflight state for every static binding root.",
		},
		[]string{"root", "adapter"},
	)
)

// EphemeralMessage is an intentionally non-durable delivery hint. Its payload
// is already serialized by an object-level typed event codec.
type EphemeralMessage struct {
	Channel string
	Payload []byte
}

// EphemeralDelivery is one provider-neutral Pub/Sub delivery.
type EphemeralDelivery struct {
	Channel string
	Payload []byte
}

// EphemeralSubscription is an explicitly non-durable subscription. Durable
// object facts must use DurableDeliveryTransport instead.
type EphemeralSubscription interface {
	Channel() <-chan EphemeralDelivery
	Close() error
}

// DurableField is a transport record field. Object event schemas remain in
// metadata and their generated codec; they are never redefined by this port.
type DurableField struct {
	Name  string
	Value string
}

// DurableMessage is an append-only delivery record for a Redis Stream.
type DurableMessage struct {
	Stream string
	Fields []DurableField
}

// MessageTransport is the provider-neutral runtime boundary. Pub/Sub remains
// ephemeral while durable cross-service facts are appended to a Stream.
type MessageTransport interface {
	PublishEphemeral(context.Context, EphemeralMessage) error
	SubscribeEphemeral(context.Context, ...string) (EphemeralSubscription, error)
	AppendDurable(context.Context, DurableMessage) (string, error)
}

// StreamReadRequest names one object-owned consumer group operation. Stream
// and group identifiers originate from object metadata/codegen, not this
// provider boundary.
type StreamReadRequest struct {
	Stream   string
	Group    string
	Consumer string
	Count    int64
	Block    time.Duration
}

// CursorReadRequest reads immutable records strictly after Cursor without
// assigning them to a consumer group. It is intended for per-principal
// resumable delivery where every device owns its own persisted cursor.
type CursorReadRequest struct {
	Stream string
	Cursor string
	Count  int64
	Block  time.Duration
}

// StreamDelivery is a transport projection of one durable record.
type StreamDelivery struct {
	Stream string
	ID     string
	Fields []DurableField
}

// DeadLetterMessage preserves object-owned stream coordinates while the
// provider adapter handles durable append and transport observability.
type DeadLetterMessage struct {
	SourceStream      string
	DestinationStream string
	SourceID          string
	Reason            string
	Fields            []DurableField
}

// DurableDeliveryTransport makes durable consume, acknowledgement and pending
// reclaim explicit instead of treating Pub/Sub as a reliable queue.
type DurableDeliveryTransport interface {
	EnsureDurableConsumerGroup(
		ctx context.Context,
		stream, group, start string,
	) error
	ReadDurable(ctx context.Context, request StreamReadRequest) ([]StreamDelivery, error)
	AckDurable(ctx context.Context, stream, group string, ids ...string) error
	ReclaimDurable(
		ctx context.Context,
		stream, group, consumer string,
		minIdle time.Duration,
		start string,
		count int64,
	) ([]StreamDelivery, string, error)
	PublishDeadLetter(
		ctx context.Context,
		message DeadLetterMessage,
	) (string, error)
	ClaimDurableDelivery(
		ctx context.Context,
		key, value string,
		ttl time.Duration,
	) (bool, error)
	ReleaseDurableDelivery(ctx context.Context, key string) error
	SetDurableRetention(ctx context.Context, stream string, ttl time.Duration) error
}

// CursorDeliveryTransport is deliberately separate from consumer-group
// delivery: cursor reads do not ACK globally and therefore cannot make one
// device hide events from another device of the same principal.
type CursorDeliveryTransport interface {
	ReadDurableAfter(
		ctx context.Context,
		request CursorReadRequest,
	) ([]StreamDelivery, error)
}

// MessageTransportBinding 是由各服务 generated descriptor 映射出的脱敏运行时绑定。
// 它不承载 endpoint 或 Secret 的实际值。
type MessageTransportBinding struct {
	State               string
	AdapterID           string
	TimeoutMilliseconds int
}

// MessageTransportRoot 是生成 descriptor 中一个静态组合根的声明。
type MessageTransportRoot struct {
	RootID              string
	RequiredRedisScenes []string
}

// RedisSceneProvider 只暴露消息 root 已声明的 Redis scene；业务事件坐标仍属于对象 Port。
type RedisSceneProvider interface {
	LookupScene(name string) (rtredis.Client, bool)
}

// ResolvedMessageTransport 是启动预检通过后可供对象级 adapter 使用的 Redis scene 集合。
type ResolvedMessageTransport struct {
	rootID string
	scenes map[string]rtredis.Client
}

func (t ResolvedMessageTransport) RootID() string {
	return t.rootID
}

func (t ResolvedMessageTransport) Scene(name string) (rtredis.Client, bool) {
	client, ok := t.scenes[strings.TrimSpace(name)]
	return client, ok
}

// RedisMessageTransport adapts preflighted scene clients to the typed runtime
// port. It deliberately does not own object topic, stream or consumer-group
// naming.
type RedisMessageTransport struct {
	realtime rtredis.Client
	durable  rtredis.Client
	rootID   string
	adapter  string
}

func NewRedisMessageTransport(
	realtime rtredis.Client,
	durable rtredis.Client,
) (*RedisMessageTransport, error) {
	return NewRedisMessageTransportForRoot("", RedisMessageTransportAdapter, realtime, durable)
}

func NewRedisMessageTransportForRoot(
	rootID string,
	adapterID string,
	realtime rtredis.Client,
	durable rtredis.Client,
) (*RedisMessageTransport, error) {
	if realtime == nil || durable == nil {
		return nil, fmt.Errorf("Redis message transport requires realtime and durable scenes")
	}
	adapterID = strings.TrimSpace(adapterID)
	if adapterID != RedisMessageTransportAdapter && adapterID != RedisMessageTransportFixture {
		return nil, fmt.Errorf("Redis message transport has unregistered adapter %q", adapterID)
	}
	return &RedisMessageTransport{
		realtime: realtime,
		durable:  durable,
		rootID:   metricRootID(rootID),
		adapter:  adapterID,
	}, nil
}

func (t *RedisMessageTransport) PublishEphemeral(
	ctx context.Context,
	message EphemeralMessage,
) error {
	if t == nil || t.realtime == nil {
		return fmt.Errorf("Redis ephemeral transport is unavailable")
	}
	channel := strings.TrimSpace(message.Channel)
	if channel == "" {
		return fmt.Errorf("Redis ephemeral channel is required")
	}
	if len(message.Payload) == 0 {
		return fmt.Errorf("Redis ephemeral payload is required")
	}
	start := time.Now()
	err := t.realtime.Publish(ctx, channel, string(message.Payload))
	t.recordOperation("ephemeral_publish", start, err)
	return err
}

func (t *RedisMessageTransport) SubscribeEphemeral(
	ctx context.Context,
	channels ...string,
) (EphemeralSubscription, error) {
	if t == nil || t.realtime == nil {
		return nil, fmt.Errorf("Redis ephemeral transport is unavailable")
	}
	normalized := make([]string, 0, len(channels))
	seen := make(map[string]struct{}, len(channels))
	for _, rawChannel := range channels {
		channel := strings.TrimSpace(rawChannel)
		if channel == "" {
			return nil, fmt.Errorf("Redis ephemeral subscription has an empty channel")
		}
		if _, duplicate := seen[channel]; duplicate {
			return nil, fmt.Errorf("Redis ephemeral subscription channel %s is duplicated", channel)
		}
		seen[channel] = struct{}{}
		normalized = append(normalized, channel)
	}
	if len(normalized) == 0 {
		return nil, fmt.Errorf("Redis ephemeral subscription requires at least one channel")
	}
	start := time.Now()
	source, err := t.realtime.Subscribe(ctx, normalized...)
	t.recordOperation("ephemeral_subscribe", start, err)
	if err != nil {
		return nil, err
	}
	if source == nil {
		return nil, fmt.Errorf("Redis ephemeral subscription returned no source")
	}
	return newRedisEphemeralSubscription(ctx, source), nil
}

type redisEphemeralSubscription struct {
	source    rtredis.Subscription
	messages  chan EphemeralDelivery
	done      chan struct{}
	closeOnce sync.Once
	closeErr  error
}

func newRedisEphemeralSubscription(
	ctx context.Context,
	source rtredis.Subscription,
) *redisEphemeralSubscription {
	subscription := &redisEphemeralSubscription{
		source:   source,
		messages: make(chan EphemeralDelivery),
		done:     make(chan struct{}),
	}
	go subscription.forward(ctx)
	return subscription
}

func (s *redisEphemeralSubscription) Channel() <-chan EphemeralDelivery {
	return s.messages
}

func (s *redisEphemeralSubscription) Close() error {
	s.closeSource()
	return s.closeErr
}

func (s *redisEphemeralSubscription) closeSource() {
	s.closeOnce.Do(func() {
		close(s.done)
		s.closeErr = s.source.Close()
	})
}

func (s *redisEphemeralSubscription) forward(ctx context.Context) {
	defer close(s.messages)
	defer s.closeSource()
	for {
		select {
		case <-ctx.Done():
			return
		case <-s.done:
			return
		case message, ok := <-s.source.Channel():
			if !ok {
				return
			}
			delivery := EphemeralDelivery{
				Channel: message.Channel,
				Payload: []byte(message.Payload),
			}
			select {
			case <-ctx.Done():
				return
			case <-s.done:
				return
			case s.messages <- delivery:
			}
		}
	}
}

func (t *RedisMessageTransport) AppendDurable(
	ctx context.Context,
	message DurableMessage,
) (string, error) {
	if t == nil || t.durable == nil {
		return "", fmt.Errorf("Redis durable transport is unavailable")
	}
	stream := strings.TrimSpace(message.Stream)
	if stream == "" {
		return "", fmt.Errorf("Redis durable stream is required")
	}
	if len(message.Fields) == 0 {
		return "", fmt.Errorf("Redis durable record fields are required")
	}
	values := make(map[string]string, len(message.Fields))
	for _, field := range message.Fields {
		name := strings.TrimSpace(field.Name)
		if name == "" {
			return "", fmt.Errorf("Redis durable record has empty field name")
		}
		if _, duplicate := values[name]; duplicate {
			return "", fmt.Errorf("Redis durable record field %s is duplicated", name)
		}
		values[name] = field.Value
	}
	start := time.Now()
	id, err := t.durable.XAdd(ctx, stream, values)
	t.recordOperation("durable_append", start, err)
	return id, err
}

func (t *RedisMessageTransport) EnsureDurableConsumerGroup(
	ctx context.Context,
	stream, group, start string,
) error {
	if t == nil || t.durable == nil {
		return fmt.Errorf("Redis durable transport is unavailable")
	}
	stream = strings.TrimSpace(stream)
	group = strings.TrimSpace(group)
	start = strings.TrimSpace(start)
	if stream == "" || group == "" || start == "" {
		return fmt.Errorf("Redis durable consumer group requires stream, group and start")
	}
	started := time.Now()
	err := t.durable.XGroupCreateMkStream(ctx, stream, group, start)
	t.recordOperation("durable_group_ensure", started, err)
	return err
}

func (t *RedisMessageTransport) ReadDurable(
	ctx context.Context,
	request StreamReadRequest,
) ([]StreamDelivery, error) {
	if t == nil || t.durable == nil {
		return nil, fmt.Errorf("Redis durable transport is unavailable")
	}
	stream := strings.TrimSpace(request.Stream)
	group := strings.TrimSpace(request.Group)
	consumer := strings.TrimSpace(request.Consumer)
	if stream == "" || group == "" || consumer == "" || request.Count <= 0 || request.Block <= 0 {
		return nil, fmt.Errorf("Redis durable read requires stream, group, consumer, positive count and block")
	}
	started := time.Now()
	records, err := t.durable.XReadGroup(
		ctx,
		group,
		consumer,
		map[string]string{stream: ">"},
		request.Count,
		request.Block,
	)
	if err != nil {
		t.recordOperation("durable_consume", started, err)
		return nil, err
	}
	t.recordOperation("durable_consume", started, nil)
	t.observePending(ctx, stream, group)
	return streamDeliveries(records), nil
}

func (t *RedisMessageTransport) ReadDurableAfter(
	ctx context.Context,
	request CursorReadRequest,
) ([]StreamDelivery, error) {
	if t == nil || t.durable == nil {
		return nil, fmt.Errorf("Redis durable transport is unavailable")
	}
	stream := strings.TrimSpace(request.Stream)
	cursor := strings.TrimSpace(request.Cursor)
	if stream == "" || cursor == "" || request.Count <= 0 || request.Block < 0 {
		return nil, fmt.Errorf(
			"Redis cursor read requires stream, cursor, positive count and non-negative block",
		)
	}
	started := time.Now()
	records, err := t.durable.XRead(
		ctx,
		map[string]string{stream: cursor},
		request.Count,
		request.Block,
	)
	t.recordOperation("durable_cursor_read", started, err)
	if err != nil {
		return nil, err
	}
	return streamDeliveries(records), nil
}

func (t *RedisMessageTransport) AckDurable(
	ctx context.Context,
	stream, group string,
	ids ...string,
) error {
	if t == nil || t.durable == nil {
		return fmt.Errorf("Redis durable transport is unavailable")
	}
	if strings.TrimSpace(stream) == "" || strings.TrimSpace(group) == "" || len(ids) == 0 {
		return fmt.Errorf("Redis durable acknowledgement requires stream, group and record IDs")
	}
	started := time.Now()
	err := t.durable.XAck(ctx, stream, group, ids...)
	t.recordOperation("durable_ack", started, err)
	if err == nil {
		t.observePending(ctx, strings.TrimSpace(stream), strings.TrimSpace(group))
	}
	return err
}

func (t *RedisMessageTransport) ReclaimDurable(
	ctx context.Context,
	stream, group, consumer string,
	minIdle time.Duration,
	start string,
	count int64,
) ([]StreamDelivery, string, error) {
	if t == nil || t.durable == nil {
		return nil, "", fmt.Errorf("Redis durable transport is unavailable")
	}
	if strings.TrimSpace(stream) == "" ||
		strings.TrimSpace(group) == "" ||
		strings.TrimSpace(consumer) == "" ||
		strings.TrimSpace(start) == "" ||
		minIdle < 0 ||
		count <= 0 {
		return nil, "", fmt.Errorf("Redis durable reclaim requires stream, group, consumer, cursor and positive count")
	}
	started := time.Now()
	records, next, err := t.durable.XAutoClaim(ctx, stream, group, consumer, minIdle, start, count)
	if err != nil {
		t.recordOperation("durable_reclaim", started, err)
		return nil, "", err
	}
	t.recordOperation("durable_reclaim", started, nil)
	t.observePending(ctx, strings.TrimSpace(stream), strings.TrimSpace(group))
	return streamDeliveries(records), next, nil
}

func (t *RedisMessageTransport) PublishDeadLetter(
	ctx context.Context,
	message DeadLetterMessage,
) (string, error) {
	sourceStream := strings.TrimSpace(message.SourceStream)
	destinationStream := strings.TrimSpace(message.DestinationStream)
	sourceID := strings.TrimSpace(message.SourceID)
	reason := strings.TrimSpace(message.Reason)
	if sourceStream == "" || sourceID == "" || reason == "" {
		return "", fmt.Errorf("Redis dead-letter requires source stream, record ID and reason")
	}
	if destinationStream == "" {
		destinationStream = sourceStream + ".dlq"
	}
	deadLetterFields := make([]DurableField, 0, len(message.Fields)+2)
	deadLetterFields = append(deadLetterFields,
		DurableField{Name: "sourceId", Value: sourceID},
		DurableField{Name: "reason", Value: reason},
	)
	deadLetterFields = append(deadLetterFields, message.Fields...)
	id, err := t.AppendDurable(ctx, DurableMessage{
		Stream: destinationStream,
		Fields: deadLetterFields,
	})
	if err == nil {
		messageTransportDeadLetters.WithLabelValues(
			t.metricRootID(),
			t.metricAdapterID(),
			sourceStream,
			reason,
		).Inc()
	}
	return id, err
}

func (t *RedisMessageTransport) ClaimDurableDelivery(
	ctx context.Context,
	key, value string,
	ttl time.Duration,
) (bool, error) {
	if t == nil || t.durable == nil {
		return false, fmt.Errorf("Redis durable transport is unavailable")
	}
	key = strings.TrimSpace(key)
	if key == "" || strings.TrimSpace(value) == "" || ttl <= 0 {
		return false, fmt.Errorf("Redis durable delivery claim requires key, value and positive TTL")
	}
	started := time.Now()
	claimed, err := t.durable.SetNX(ctx, key, value, ttl)
	t.recordOperation("durable_delivery_claim", started, err)
	return claimed, err
}

func (t *RedisMessageTransport) ReleaseDurableDelivery(
	ctx context.Context,
	key string,
) error {
	if t == nil || t.durable == nil {
		return fmt.Errorf("Redis durable transport is unavailable")
	}
	key = strings.TrimSpace(key)
	if key == "" {
		return fmt.Errorf("Redis durable delivery release requires key")
	}
	started := time.Now()
	err := t.durable.Del(ctx, key)
	t.recordOperation("durable_delivery_release", started, err)
	return err
}

func (t *RedisMessageTransport) SetDurableRetention(
	ctx context.Context,
	stream string,
	ttl time.Duration,
) error {
	if t == nil || t.durable == nil {
		return fmt.Errorf("Redis durable transport is unavailable")
	}
	stream = strings.TrimSpace(stream)
	if stream == "" || ttl <= 0 {
		return fmt.Errorf("Redis durable retention requires stream and positive TTL")
	}
	started := time.Now()
	err := t.durable.XTrimOlderThan(ctx, stream, ttl)
	if err == nil {
		// Key expiry bounds inactive streams; MINID trimming bounds entries in
		// continuously active streams where EXPIRE alone would slide forever.
		err = t.durable.Expire(ctx, stream, ttl)
	}
	t.recordOperation("durable_retention", started, err)
	return err
}

func (t *RedisMessageTransport) recordOperation(operation string, started time.Time, err error) {
	status := "ok"
	if err != nil {
		status = "error"
	}
	messageTransportOperations.WithLabelValues(
		t.metricRootID(),
		t.metricAdapterID(),
		operation,
		status,
	).Inc()
	messageTransportLatency.WithLabelValues(
		t.metricRootID(),
		t.metricAdapterID(),
		operation,
	).Observe(time.Since(started).Seconds())
}

func (t *RedisMessageTransport) observePending(ctx context.Context, stream, group string) {
	pending, err := t.durable.XPendingCount(ctx, stream, group)
	if err != nil {
		t.recordOperation("pending_lag_probe", time.Now(), err)
		return
	}
	messageTransportPending.WithLabelValues(
		t.metricRootID(),
		t.metricAdapterID(),
		stream,
		group,
	).Set(float64(pending))
}

func (t *RedisMessageTransport) metricRootID() string {
	if t == nil {
		return "unbound"
	}
	return metricRootID(t.rootID)
}

func (t *RedisMessageTransport) metricAdapterID() string {
	if t == nil || strings.TrimSpace(t.adapter) == "" {
		return RedisMessageTransportAdapter
	}
	return t.adapter
}

func metricRootID(rootID string) string {
	if normalized := strings.TrimSpace(rootID); normalized != "" {
		return normalized
	}
	return "unbound"
}

func streamDeliveries(records []rtredis.StreamMessage) []StreamDelivery {
	deliveries := make([]StreamDelivery, 0, len(records))
	for _, record := range records {
		keys := make([]string, 0, len(record.Values))
		for key := range record.Values {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		fields := make([]DurableField, 0, len(keys))
		for _, key := range keys {
			fields = append(fields, DurableField{Name: key, Value: record.Values[key]})
		}
		deliveries = append(deliveries, StreamDelivery{
			Stream: record.Stream,
			ID:     record.ID,
			Fields: fields,
		})
	}
	return deliveries
}

// RequireRedisMessageTransport 在任何 publisher/consumer 构造前验证 generated Binding、
// root 声明、scene 存在性与 Redis 健康。调用方不得将失败降级为 WARN、memory 或跳过消费。
func RequireRedisMessageTransport(
	ctx context.Context,
	binding MessageTransportBinding,
	root MessageTransportRoot,
	scenes RedisSceneProvider,
) (ResolvedMessageTransport, error) {
	rootID := strings.TrimSpace(root.RootID)
	if rootID == "" {
		return ResolvedMessageTransport{}, fmt.Errorf("message transport root is required")
	}
	adapterID := strings.TrimSpace(binding.AdapterID)
	if adapterID == "" {
		adapterID = "unbound"
	}
	messageTransportPreflight.WithLabelValues(rootID, adapterID).Set(0)
	if binding.State != "enabled" {
		return ResolvedMessageTransport{}, fmt.Errorf(
			"message transport binding for root %s is not enabled",
			rootID,
		)
	}
	if binding.AdapterID != RedisMessageTransportAdapter &&
		binding.AdapterID != RedisMessageTransportFixture {
		return ResolvedMessageTransport{}, fmt.Errorf(
			"message transport root %s has an unregistered Redis adapter %s",
			rootID,
			binding.AdapterID,
		)
	}
	if binding.TimeoutMilliseconds <= 0 {
		return ResolvedMessageTransport{}, fmt.Errorf(
			"message transport root %s has invalid timeout",
			rootID,
		)
	}
	if scenes == nil || len(root.RequiredRedisScenes) == 0 {
		return ResolvedMessageTransport{}, fmt.Errorf(
			"message transport root %s has no declared Redis scenes",
			rootID,
		)
	}
	timeout := time.Duration(binding.TimeoutMilliseconds) * time.Millisecond
	resolved := ResolvedMessageTransport{
		rootID: rootID,
		scenes: make(map[string]rtredis.Client, len(root.RequiredRedisScenes)),
	}
	for _, rawScene := range root.RequiredRedisScenes {
		scene := strings.TrimSpace(rawScene)
		if scene == "" {
			return ResolvedMessageTransport{}, fmt.Errorf(
				"message transport root %s declares an empty Redis scene",
				rootID,
			)
		}
		if _, duplicate := resolved.scenes[scene]; duplicate {
			return ResolvedMessageTransport{}, fmt.Errorf(
				"message transport root %s declares Redis scene %s more than once",
				rootID,
				scene,
			)
		}
		client, ok := scenes.LookupScene(scene)
		if !ok || client == nil {
			return ResolvedMessageTransport{}, fmt.Errorf(
				"message transport root %s requires unavailable Redis scene %s",
				rootID,
				scene,
			)
		}
		pingCtx, cancel := context.WithTimeout(ctx, timeout)
		err := client.Ping(pingCtx)
		cancel()
		if err != nil {
			return ResolvedMessageTransport{}, fmt.Errorf(
				"message transport root %s Redis scene %s preflight: %w",
				rootID,
				scene,
				err,
			)
		}
		resolved.scenes[scene] = client
	}
	messageTransportPreflight.WithLabelValues(rootID, binding.AdapterID).Set(1)
	return resolved, nil
}

// RequireConfiguredRedisMessageTransport is the shared composition helper for
// generated descriptor bindings. It validates the selected binding before any
// publisher or consumer is constructed; only an Alpha descriptor may select the
// isolated local fixture.
func RequireConfiguredRedisMessageTransport(
	ctx context.Context,
	environment string,
	found bool,
	binding MessageTransportBinding,
	root MessageTransportRoot,
	router *rtredis.Router,
	sceneModes map[string]string,
) (ResolvedMessageTransport, error) {
	if !found {
		return ResolvedMessageTransport{}, fmt.Errorf(
			"%s binding is missing for environment=%s",
			RuntimeMessageTransportCapability,
			environment,
		)
	}
	environment = strings.TrimSpace(environment)
	switch environment {
	case "alpha", "beta", "gamma", "prod":
	default:
		return ResolvedMessageTransport{}, fmt.Errorf(
			"message transport has unknown environment=%s",
			environment,
		)
	}
	fixture := binding.AdapterID == RedisMessageTransportFixture
	if fixture && environment != "alpha" {
		return ResolvedMessageTransport{}, fmt.Errorf(
			"message transport root %s may select the Redis fixture only in alpha",
			root.RootID,
		)
	}
	transport, err := RequireRedisMessageTransport(ctx, binding, root, router)
	if err != nil {
		return ResolvedMessageTransport{}, err
	}
	if fixture {
		return transport, nil
	}
	for _, scene := range root.RequiredRedisScenes {
		if !isRealRedisSceneMode(sceneModes[strings.TrimSpace(scene)]) {
			return ResolvedMessageTransport{}, fmt.Errorf(
				"message transport root %s requires real Redis scene %s outside the alpha fixture branch",
				root.RootID,
				scene,
			)
		}
	}
	return transport, nil
}

func isRealRedisSceneMode(mode string) bool {
	switch strings.ToLower(strings.TrimSpace(mode)) {
	case "standalone", "cluster":
		return true
	default:
		return false
	}
}
