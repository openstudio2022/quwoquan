package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"

	runtimeobservability "quwoquan_service/runtime/observability"
	eventrecord "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	recoverydomain "quwoquan_service/services/product-ops-service/internal/product_ops/recovery_failure/domain"
)

var (
	ErrInvalidRecoveryFailure  = errors.New("invalid recovery failure")
	ErrRecoverySinkUnavailable = errors.New("recovery failure sink unavailable")
)

var (
	sensitiveAssignmentPattern = regexp.MustCompile(`(?i)(access[_-]?token|refresh[_-]?token|authorization|cookie)\s*[:=]\s*[^\s,;]+`)
	emailPattern               = regexp.MustCompile(`(?i)[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}`)
	phonePattern               = regexp.MustCompile(`(?:\+?86[- ]?)?1[3-9][0-9]{9}`)
	userPathPattern            = regexp.MustCompile(`(?i)(/Users/|/home/|\\Users\\)[^/\\\s]+`)
	urlQueryPattern            = regexp.MustCompile(`(https://[^\s?#]+)\?[^\s#]*`)
)

type Failure = recoverydomain.Failure

type Reporter interface {
	ReportRecoveryFailure(context.Context, string, map[string]string) (eventrecord.EventBatchAck, error)
}

type Service struct {
	reporter Reporter
	now      func() time.Time
}

func NewService(reporter Reporter) *Service {
	return &Service{reporter: reporter, now: time.Now}
}

func (s *Service) Report(ctx context.Context, failure Failure) error {
	if s.reporter == nil {
		return ErrRecoverySinkUnavailable
	}
	normalized, err := s.normalize(failure)
	if err != nil {
		return err
	}
	canonical, _ := json.Marshal(normalized)
	digest := sha256.Sum256(canonical)
	batchKey := hex.EncodeToString(digest[:])
	signal := "app.exception.platform"
	if normalized.ErrorSource == "flutter" {
		signal = "app.exception.flutter"
	}
	fields := map[string]string{
		"schema":             runtimeobservability.ObservabilitySchema,
		"occurredAt":         normalized.OccurredAt,
		"observedAt":         s.now().UTC().Format(time.RFC3339Nano),
		"logKind":            "exception",
		"severity":           "ERROR",
		"signal":             signal,
		"message":            normalized.ErrorMessage,
		"resourceSourceType": "app",
		"resourceService":    "quwoquan_app",
		"resourceAppVersion": normalized.AppVersion,
		"buildNumber":        normalized.BuildNumber,
		"platform":           normalized.Platform,
		"osVersion":          normalized.OSVersion,
		"deviceModel":        normalized.DeviceModel,
		"errorSource":        normalized.ErrorSource,
		"errorType":          normalized.ErrorType,
		"stackTrace":         normalized.StackTrace,
	}
	if _, err := s.reporter.ReportRecoveryFailure(ctx, batchKey, fields); err != nil {
		if errors.Is(err, eventrecord.ErrInvalidRuntimeLogBatch) {
			return fmt.Errorf("%w: %v", ErrInvalidRecoveryFailure, err)
		}
		return fmt.Errorf("%w: %v", ErrRecoverySinkUnavailable, err)
	}
	return nil
}

func (s *Service) normalize(failure Failure) (Failure, error) {
	failure.OccurredAt = strings.TrimSpace(failure.OccurredAt)
	failure.AppVersion = strings.TrimSpace(failure.AppVersion)
	failure.BuildNumber = strings.TrimSpace(failure.BuildNumber)
	failure.Platform = strings.ToLower(strings.TrimSpace(failure.Platform))
	failure.OSVersion = strings.TrimSpace(failure.OSVersion)
	failure.DeviceModel = strings.TrimSpace(failure.DeviceModel)
	failure.ErrorSource = strings.ToLower(strings.TrimSpace(failure.ErrorSource))
	failure.ErrorType = strings.TrimSpace(failure.ErrorType)
	failure.ErrorMessage = sanitize(failure.ErrorMessage)
	failure.StackTrace = sanitize(failure.StackTrace)
	occurredAt, occurredErr := time.Parse(time.RFC3339Nano, failure.OccurredAt)
	now := s.now().UTC()
	if occurredErr != nil || failure.Validate(now) != nil {
		return Failure{}, ErrInvalidRecoveryFailure
	}
	failure.OccurredAt = occurredAt.UTC().Format(time.RFC3339Nano)
	return failure, nil
}

func sanitize(raw string) string {
	value := strings.TrimSpace(raw)
	value = sensitiveAssignmentPattern.ReplaceAllString(value, "$1=<redacted>")
	value = emailPattern.ReplaceAllString(value, "<redacted-email>")
	value = phonePattern.ReplaceAllString(value, "<redacted-phone>")
	value = userPathPattern.ReplaceAllString(value, "$1<redacted>")
	value = urlQueryPattern.ReplaceAllString(value, "$1?<redacted>")
	return value
}
