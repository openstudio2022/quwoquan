// Package mq consumes RTC durable account-security terminal facts.
package mq

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application"
)

const (
	UserAccountSecurityEventStream = "events.user.account"
	UserAccountSecurityDLQ         = "events.user.account.rtc-service.dlq"

	userAccountSecurityConsumerGroup       = "rtc-service-user-account-security"
	userAccountSecurityDLQTTL              = 7 * 24 * time.Hour
	defaultSecurityBatchSize         int64 = 50
	defaultSecurityMaxAttempts       int64 = 5
	defaultSecurityMinIdle                 = 30 * time.Second
	defaultSecurityPollInterval            = 250 * time.Millisecond
	defaultSecurityReadBlock               = 100 * time.Millisecond
)

var (
	errUnsupportedUserAccountSecurityEvent = errors.New(
		"unsupported user account security event",
	)
	rtcAccountSecurityConsumerTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "rtc_account_security_consumer_total",
			Help: "RTC account-security durable consumer outcomes.",
		},
		[]string{"event_class", "outcome"},
	)
	rtcAccountSecurityConsumerDuration = promauto.NewHistogram(
		prometheus.HistogramOpts{
			Name:    "rtc_account_security_consumer_duration_seconds",
			Help:    "RTC account-security terminal event application duration.",
			Buckets: prometheus.DefBuckets,
		},
	)
)

// AccountSecurityDurableTransport keeps the source PEL available for explicit
// recovery. Dead letters contain only digests, never the source payload.
type AccountSecurityDurableTransport interface {
	runtimemessaging.MessageTransport
	runtimemessaging.DurableDeliveryTransport
}

type AccountSecurityFailureStore interface {
	RecordAccountSecurityFailure(
		ctx context.Context,
		stream string,
		messageID string,
		eventID string,
		errorClass string,
		cause error,
	) (int64, error)
	IsAccountSecurityDeadLettered(
		ctx context.Context,
		stream string,
		messageID string,
	) (bool, error)
	MarkAccountSecurityDeadLettered(
		ctx context.Context,
		stream string,
		messageID string,
	) error
	ClearAccountSecurityFailure(
		ctx context.Context,
		stream string,
		messageID string,
	) error
}

type UserAccountSecurityConsumerConfig struct {
	BatchSize    int64
	MaxAttempts  int64
	MinIdle      time.Duration
	PollInterval time.Duration
	ReadBlock    time.Duration
}

func DefaultUserAccountSecurityConsumerConfig() UserAccountSecurityConsumerConfig {
	return UserAccountSecurityConsumerConfig{
		BatchSize:    defaultSecurityBatchSize,
		MaxAttempts:  defaultSecurityMaxAttempts,
		MinIdle:      defaultSecurityMinIdle,
		PollInterval: defaultSecurityPollInterval,
		ReadBlock:    defaultSecurityReadBlock,
	}
}

func (config UserAccountSecurityConsumerConfig) withDefaults() UserAccountSecurityConsumerConfig {
	defaults := DefaultUserAccountSecurityConsumerConfig()
	if config.BatchSize <= 0 {
		config.BatchSize = defaults.BatchSize
	}
	if config.MaxAttempts <= 0 {
		config.MaxAttempts = defaults.MaxAttempts
	}
	if config.MinIdle < 0 {
		config.MinIdle = defaults.MinIdle
	}
	if config.PollInterval <= 0 {
		config.PollInterval = defaults.PollInterval
	}
	if config.ReadBlock <= 0 {
		config.ReadBlock = defaults.ReadBlock
	}
	return config
}

type UserAccountSecurityConsumer struct {
	transport AccountSecurityDurableTransport
	closer    application.AccountSecurityTerminalCloser
	failures  AccountSecurityFailureStore
	consumer  string
	config    UserAccountSecurityConsumerConfig
	logger    *slog.Logger

	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure string
}

func NewUserAccountSecurityConsumer(
	transport AccountSecurityDurableTransport,
	closer application.AccountSecurityTerminalCloser,
	failures AccountSecurityFailureStore,
	consumer string,
	logger *slog.Logger,
	config UserAccountSecurityConsumerConfig,
) (*UserAccountSecurityConsumer, error) {
	if transport == nil || closer == nil || failures == nil {
		return nil, errors.New(
			"rtc account security consumer requires transport, closer and failure store",
		)
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return nil, errors.New("rtc account security consumer name is required")
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &UserAccountSecurityConsumer{
		transport: transport,
		closer:    closer,
		failures:  failures,
		consumer:  consumer,
		config:    config.withDefaults(),
		logger:    logger,
	}, nil
}

func (consumer *UserAccountSecurityConsumer) EnsureGroup(
	ctx context.Context,
) error {
	if consumer == nil || consumer.transport == nil {
		return errors.New("rtc account security consumer is not configured")
	}
	if err := consumer.transport.EnsureDurableConsumerGroup(
		ctx,
		UserAccountSecurityEventStream,
		userAccountSecurityConsumerGroup,
		"0",
	); err != nil {
		return fmt.Errorf("ensure rtc account security consumer group: %w", err)
	}
	return nil
}

func (consumer *UserAccountSecurityConsumer) ProcessOnce(
	ctx context.Context,
) (int, error) {
	if consumer == nil || consumer.transport == nil || consumer.closer == nil ||
		consumer.failures == nil {
		return 0, errors.New("rtc account security consumer is not configured")
	}
	if err := consumer.EnsureGroup(ctx); err != nil {
		consumer.recordFailure(err)
		return 0, err
	}
	claimed, _, err := consumer.transport.ReclaimDurable(
		ctx,
		UserAccountSecurityEventStream,
		userAccountSecurityConsumerGroup,
		consumer.consumer,
		consumer.config.MinIdle,
		"0-0",
		consumer.config.BatchSize,
	)
	if err != nil {
		err = fmt.Errorf("reclaim rtc account security events: %w", err)
		consumer.recordFailure(err)
		return 0, err
	}
	fresh, err := consumer.transport.ReadDurable(
		ctx,
		runtimemessaging.StreamReadRequest{
			Stream:   UserAccountSecurityEventStream,
			Group:    userAccountSecurityConsumerGroup,
			Consumer: consumer.consumer,
			Count:    consumer.config.BatchSize,
			Block:    consumer.config.ReadBlock,
		},
	)
	if err != nil {
		err = fmt.Errorf("read rtc account security events: %w", err)
		consumer.recordFailure(err)
		return 0, err
	}

	processed := 0
	var firstErr error
	for _, message := range uniqueAccountSecurityMessages(claimed, fresh) {
		if err := consumer.processMessage(ctx, message); err != nil {
			if firstErr == nil {
				firstErr = err
			}
			continue
		}
		processed++
	}
	if firstErr != nil {
		consumer.recordFailure(firstErr)
		return processed, firstErr
	}
	consumer.recordSuccess()
	return processed, nil
}

func (consumer *UserAccountSecurityConsumer) Run(ctx context.Context) {
	ticker := time.NewTicker(consumer.config.PollInterval)
	defer ticker.Stop()
	for {
		if _, err := consumer.ProcessOnce(ctx); err != nil && ctx.Err() == nil {
			consumer.logger.ErrorContext(
				ctx,
				"rtc account security consumer scan failed",
				slog.String("errorDigest", accountSecurityErrorDigest(err)),
			)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (consumer *UserAccountSecurityConsumer) Healthy(
	maxStaleness time.Duration,
) error {
	if consumer == nil {
		return errors.New("rtc account security consumer is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	consumer.mu.RLock()
	defer consumer.mu.RUnlock()
	if consumer.lastSuccess.IsZero() {
		return errors.New("rtc account security consumer has not completed a scan")
	}
	if consumer.lastFailure != "" {
		return errors.New("rtc account security consumer last scan failed")
	}
	if time.Since(consumer.lastSuccess) > maxStaleness {
		return errors.New("rtc account security consumer heartbeat is stale")
	}
	return nil
}

// RecoverDeadLetter clears the held-DLQ marker so the next eligible PEL
// reclaim retries the source delivery. It does not recreate rooms or sessions
// itself; only a replayed terminal event may close the current authoritative
// state.
func (consumer *UserAccountSecurityConsumer) RecoverDeadLetter(
	ctx context.Context,
	sourceStreamID string,
) error {
	if consumer == nil || consumer.failures == nil {
		return errors.New("rtc account security consumer is not configured")
	}
	sourceStreamID = strings.TrimSpace(sourceStreamID)
	if sourceStreamID == "" {
		return errors.New("rtc account security recovery source stream ID is required")
	}
	deadLettered, err := consumer.failures.IsAccountSecurityDeadLettered(
		ctx,
		UserAccountSecurityEventStream,
		sourceStreamID,
	)
	if err != nil {
		return fmt.Errorf(
			"verify rtc account security dead-letter state before recovery: %w",
			err,
		)
	}
	if !deadLettered {
		return nil
	}
	return consumer.failures.ClearAccountSecurityFailure(
		ctx,
		UserAccountSecurityEventStream,
		sourceStreamID,
	)
}

func (consumer *UserAccountSecurityConsumer) processMessage(
	ctx context.Context,
	message runtimemessaging.StreamDelivery,
) error {
	values := durableFieldsToMap(message.Fields)
	eventClass := accountSecurityEventClass(values["eventName"])

	deadLettered, err := consumer.failures.IsAccountSecurityDeadLettered(
		ctx,
		UserAccountSecurityEventStream,
		message.ID,
	)
	if err != nil {
		return fmt.Errorf("read rtc account security failure state: %w", err)
	}
	if deadLettered {
		rtcAccountSecurityConsumerTotal.WithLabelValues(
			eventClass,
			"held_for_recovery",
		).Inc()
		return nil
	}

	securityEvent, err := decodeUserAccountSecurityEvent(message)
	if errors.Is(err, errUnsupportedUserAccountSecurityEvent) {
		if ackErr := consumer.ackAndClear(ctx, message.ID); ackErr != nil {
			return ackErr
		}
		rtcAccountSecurityConsumerTotal.WithLabelValues(eventClass, "ignored").Inc()
		return nil
	}

	startedAt := time.Now()
	errorClass := "invalid_event"
	if err == nil {
		result, applyErr := consumer.closer.ApplyAccountSecurityTerminalEvent(
			ctx,
			securityEvent,
		)
		err = applyErr
		if err == nil {
			if ackErr := consumer.ackAndClear(ctx, message.ID); ackErr != nil {
				return ackErr
			}
			outcome := "applied"
			switch {
			case result.RestoredIgnored:
				outcome = "restore_ignored"
			case result.Replayed:
				outcome = "replayed"
			}
			rtcAccountSecurityConsumerTotal.WithLabelValues(eventClass, outcome).Inc()
			rtcAccountSecurityConsumerDuration.Observe(time.Since(startedAt).Seconds())
			return nil
		}
		errorClass = "apply_failed"
	}

	attempts, recordErr := consumer.failures.RecordAccountSecurityFailure(
		ctx,
		UserAccountSecurityEventStream,
		message.ID,
		values["eventId"],
		errorClass,
		err,
	)
	if recordErr != nil {
		held, heldErr := consumer.failures.IsAccountSecurityDeadLettered(
			ctx,
			UserAccountSecurityEventStream,
			message.ID,
		)
		if heldErr == nil && held {
			rtcAccountSecurityConsumerTotal.WithLabelValues(
				eventClass,
				"held_for_recovery",
			).Inc()
			return nil
		}
		return fmt.Errorf("record rtc account security failure: %w", recordErr)
	}
	if attempts < consumer.config.MaxAttempts {
		rtcAccountSecurityConsumerTotal.WithLabelValues(eventClass, "retry").Inc()
		return errors.New("rtc account security terminal event processing failed")
	}
	if _, dlqErr := consumer.transport.PublishDeadLetter(
		ctx,
		runtimemessaging.DeadLetterMessage{
			SourceStream:      UserAccountSecurityEventStream,
			DestinationStream: UserAccountSecurityDLQ,
			SourceID:          message.ID,
			Reason:            "rtc_account_security_terminal_apply_failed",
			Fields: accountSecurityDeadLetterFields(
				message,
				err,
				attempts,
				errorClass,
			),
		},
	); dlqErr != nil {
		return fmt.Errorf("append rtc account security DLQ: %w", dlqErr)
	}
	if retentionErr := consumer.transport.SetDurableRetention(
		ctx,
		UserAccountSecurityDLQ,
		userAccountSecurityDLQTTL,
	); retentionErr != nil {
		return fmt.Errorf("set rtc account security DLQ retention: %w", retentionErr)
	}
	if markErr := consumer.failures.MarkAccountSecurityDeadLettered(
		ctx,
		UserAccountSecurityEventStream,
		message.ID,
	); markErr != nil {
		return fmt.Errorf("mark rtc account security DLQ state: %w", markErr)
	}
	rtcAccountSecurityConsumerTotal.WithLabelValues(eventClass, "dlq").Inc()
	consumer.logger.ErrorContext(
		ctx,
		"rtc account security terminal event moved to DLQ",
		slog.String("errorDigest", accountSecurityErrorDigest(err)),
		slog.String("eventClass", eventClass),
		slog.Int64("attempts", attempts),
	)
	return nil
}

func (consumer *UserAccountSecurityConsumer) ackAndClear(
	ctx context.Context,
	messageID string,
) error {
	if err := consumer.transport.AckDurable(
		ctx,
		UserAccountSecurityEventStream,
		userAccountSecurityConsumerGroup,
		messageID,
	); err != nil {
		return fmt.Errorf("ack rtc account security event: %w", err)
	}
	if err := consumer.failures.ClearAccountSecurityFailure(
		ctx,
		UserAccountSecurityEventStream,
		messageID,
	); err != nil {
		return fmt.Errorf("clear rtc account security failure: %w", err)
	}
	return nil
}

func (consumer *UserAccountSecurityConsumer) recordSuccess() {
	consumer.mu.Lock()
	defer consumer.mu.Unlock()
	consumer.lastSuccess = time.Now().UTC()
	consumer.lastFailure = ""
}

func (consumer *UserAccountSecurityConsumer) recordFailure(err error) {
	consumer.mu.Lock()
	defer consumer.mu.Unlock()
	consumer.lastFailure = accountSecurityErrorDigest(err)
}

func decodeUserAccountSecurityEvent(
	message runtimemessaging.StreamDelivery,
) (application.AccountSecurityTerminalEvent, error) {
	values := durableFieldsToMap(message.Fields)
	eventName := strings.TrimSpace(values["eventName"])
	switch eventName {
	case "UserAccountClosed":
		return decodeUserAccountClosedEvent(values)
	case "UserSuspended", "UserRestored":
		return decodeUserAccountEnforcementEvent(eventName, values)
	default:
		return application.AccountSecurityTerminalEvent{},
			errUnsupportedUserAccountSecurityEvent
	}
}

func decodeUserAccountClosedEvent(
	values map[string]string,
) (application.AccountSecurityTerminalEvent, error) {
	eventID, accountID, occurredAt, err := decodeUserAccountStreamIdentity(values)
	if err != nil {
		return application.AccountSecurityTerminalEvent{}, err
	}
	var payload struct {
		UserID       string   `json:"userId"`
		PersonaIDs   []string `json:"personaIds"`
		AccountState string   `json:"accountState"`
		UpdatedAt    string   `json:"updatedAt"`
	}
	if err := decodeExactAccountSecurityPayload(values["payload"], &payload); err != nil {
		return application.AccountSecurityTerminalEvent{}, err
	}
	if strings.TrimSpace(payload.UserID) != accountID ||
		strings.TrimSpace(payload.AccountState) != "closed" ||
		payload.PersonaIDs == nil {
		return application.AccountSecurityTerminalEvent{},
			errors.New("invalid closed account security payload")
	}
	if _, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(payload.UpdatedAt)); err != nil {
		return application.AccountSecurityTerminalEvent{},
			errors.New("invalid closed account security timestamp")
	}
	securityEvent := application.AccountSecurityTerminalEvent{
		EventID:      eventID,
		AccountID:    accountID,
		PersonaIDs:   payload.PersonaIDs,
		AccountState: "closed",
		OccurredAt:   occurredAt,
	}
	if err := securityEvent.Validate(); err != nil {
		return application.AccountSecurityTerminalEvent{}, err
	}
	return securityEvent, nil
}

func decodeUserAccountEnforcementEvent(
	eventName string,
	values map[string]string,
) (application.AccountSecurityTerminalEvent, error) {
	eventID, accountID, occurredAt, err := decodeUserAccountStreamIdentity(values)
	if err != nil {
		return application.AccountSecurityTerminalEvent{}, err
	}
	var payload struct {
		UserID       string   `json:"userId"`
		PersonaIDs   []string `json:"personaIds"`
		AccountState string   `json:"accountState"`
		AuthEpoch    int64    `json:"authEpoch"`
		DecisionRef  string   `json:"decisionRef"`
		OccurredAt   string   `json:"occurredAt"`
	}
	if err := decodeExactAccountSecurityPayload(values["payload"], &payload); err != nil {
		return application.AccountSecurityTerminalEvent{}, err
	}
	expectedState := "suspended"
	if eventName == "UserRestored" {
		expectedState = "active"
	}
	if strings.TrimSpace(payload.UserID) != accountID ||
		strings.TrimSpace(payload.AccountState) != expectedState ||
		payload.PersonaIDs == nil ||
		payload.AuthEpoch <= 0 ||
		strings.TrimSpace(payload.DecisionRef) == "" {
		return application.AccountSecurityTerminalEvent{},
			errors.New("invalid account security enforcement payload")
	}
	if _, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(payload.OccurredAt)); err != nil {
		return application.AccountSecurityTerminalEvent{},
			errors.New("invalid account security enforcement timestamp")
	}
	securityEvent := application.AccountSecurityTerminalEvent{
		EventID:      eventID,
		AccountID:    accountID,
		PersonaIDs:   payload.PersonaIDs,
		AccountState: expectedState,
		AuthEpoch:    payload.AuthEpoch,
		OccurredAt:   occurredAt,
	}
	if err := securityEvent.Validate(); err != nil {
		return application.AccountSecurityTerminalEvent{}, err
	}
	return securityEvent, nil
}

func decodeUserAccountStreamIdentity(
	values map[string]string,
) (string, string, time.Time, error) {
	eventID := strings.TrimSpace(values["eventId"])
	accountID := strings.TrimSpace(values["accountId"])
	accountVersion, versionErr := strconv.ParseInt(
		strings.TrimSpace(values["accountVersion"]),
		10,
		64,
	)
	occurredAt, occurredAtErr := time.Parse(
		time.RFC3339Nano,
		strings.TrimSpace(values["occurredAt"]),
	)
	if eventID == "" || accountID == "" || versionErr != nil ||
		accountVersion <= 0 || occurredAtErr != nil {
		return "", "", time.Time{},
			errors.New("invalid account security stream identity")
	}
	return eventID, accountID, occurredAt.UTC(), nil
}

func decodeExactAccountSecurityPayload(raw string, destination any) error {
	decoder := json.NewDecoder(strings.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(destination); err != nil {
		return errors.New("invalid account security payload")
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return errors.New("invalid account security payload")
	}
	return nil
}

func uniqueAccountSecurityMessages(
	groups ...[]runtimemessaging.StreamDelivery,
) []runtimemessaging.StreamDelivery {
	seen := make(map[string]struct{})
	result := make([]runtimemessaging.StreamDelivery, 0)
	for _, group := range groups {
		for _, message := range group {
			if _, duplicate := seen[message.ID]; duplicate {
				continue
			}
			seen[message.ID] = struct{}{}
			result = append(result, message)
		}
	}
	return result
}

func durableFieldsToMap(
	fields []runtimemessaging.DurableField,
) map[string]string {
	values := make(map[string]string, len(fields))
	for _, field := range fields {
		values[field.Name] = field.Value
	}
	return values
}

func accountSecurityDeadLetterFields(
	message runtimemessaging.StreamDelivery,
	cause error,
	attempts int64,
	errorClass string,
) []runtimemessaging.DurableField {
	values := durableFieldsToMap(message.Fields)
	return durableFieldsFromMap(map[string]string{
		"attempts":       strconv.FormatInt(attempts, 10),
		"contentDigest":  accountSecurityDigest(values["payload"]),
		"deadLetterId":   accountSecurityDigest(UserAccountSecurityEventStream + "\x00" + message.ID),
		"deadLetteredAt": time.Now().UTC().Format(time.RFC3339Nano),
		"errorClass":     strings.TrimSpace(errorClass),
		"errorDigest":    accountSecurityErrorDigest(cause),
		"eventClass":     accountSecurityEventClass(values["eventName"]),
		"eventDigest":    accountSecurityDigest(values["eventId"]),
		"sourceStream":   UserAccountSecurityEventStream,
		"sourceStreamId": message.ID,
	})
}

func durableFieldsFromMap(values map[string]string) []runtimemessaging.DurableField {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	fields := make([]runtimemessaging.DurableField, 0, len(keys))
	for _, key := range keys {
		fields = append(fields, runtimemessaging.DurableField{
			Name:  key,
			Value: values[key],
		})
	}
	return fields
}

func accountSecurityEventClass(eventName string) string {
	switch strings.TrimSpace(eventName) {
	case "UserAccountClosed":
		return "closed"
	case "UserSuspended":
		return "suspended"
	case "UserRestored":
		return "restored"
	default:
		return "unknown"
	}
}

func accountSecurityDigest(value string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(sum[:])
}

func accountSecurityErrorDigest(cause error) string {
	if cause == nil {
		return ""
	}
	return accountSecurityDigest(cause.Error())
}
