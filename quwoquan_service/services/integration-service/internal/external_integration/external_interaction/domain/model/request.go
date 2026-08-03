package model

import (
	"fmt"
	"strings"
	"time"
)

const (
	OperationSMSOTP     = "sms_otp.send"
	OperationPush       = "push_delivery.send"
	SensitivityPrivate  = "private"
	SensitivitySecret   = "secret"
	SensitivityInternal = "internal"
)

// SubmitRequest 是 ExternalInteraction 聚合创建命令。它只保存可靠受理所需的
// 不变量，不承载 provider attempt 或 dead-letter 的第二份状态。
type SubmitRequest struct {
	RequestID      string
	Operation      string
	Tenant         string
	Environment    string
	IdempotencyKey string
	PayloadRef     string
	PayloadDigest  string
	Sensitivity    string
	ExpiresAt      time.Time
}

func NewSubmitRequest(request SubmitRequest, now time.Time) (SubmitRequest, error) {
	request.RequestID = strings.TrimSpace(request.RequestID)
	request.Operation = strings.TrimSpace(request.Operation)
	request.Tenant = strings.TrimSpace(request.Tenant)
	request.Environment = strings.TrimSpace(request.Environment)
	request.IdempotencyKey = strings.TrimSpace(request.IdempotencyKey)
	request.PayloadRef = strings.TrimSpace(request.PayloadRef)
	request.PayloadDigest = strings.TrimSpace(request.PayloadDigest)
	request.Sensitivity = strings.TrimSpace(request.Sensitivity)
	request.ExpiresAt = request.ExpiresAt.UTC()

	if request.RequestID == "" || request.IdempotencyKey == "" {
		return SubmitRequest{}, fmt.Errorf("requestId and idempotencyKey are required")
	}
	if request.Tenant == "" || request.Environment == "" {
		return SubmitRequest{}, fmt.Errorf("tenant and env are required")
	}
	if request.PayloadRef == "" || request.PayloadDigest == "" {
		return SubmitRequest{}, fmt.Errorf("payloadRef and payloadDigest are required")
	}
	switch request.Operation {
	case OperationSMSOTP, OperationPush:
	default:
		return SubmitRequest{}, fmt.Errorf(
			"external interaction operation %q is not supported",
			request.Operation,
		)
	}
	switch request.Sensitivity {
	case SensitivityPrivate, SensitivitySecret, SensitivityInternal:
	default:
		return SubmitRequest{}, fmt.Errorf(
			"external interaction sensitivity %q is not supported",
			request.Sensitivity,
		)
	}
	if request.ExpiresAt.IsZero() || !request.ExpiresAt.After(now.UTC()) {
		return SubmitRequest{}, fmt.Errorf("expiresAt must be in the future")
	}
	return request, nil
}
