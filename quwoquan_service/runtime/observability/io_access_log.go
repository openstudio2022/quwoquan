package runtimeobservability

import (
	"fmt"
	"strings"
)

const (
	DirectionInbound  = "inbound"
	DirectionOutbound = "outbound"
)

var allowedOrigins = map[string]struct{}{
	"app.http":      {},
	"app.grpc":      {},
	"service.http":  {},
	"service.grpc":  {},
	"service.mq":    {},
	"job.internal":  {},
	"cron.internal": {},
}

var allowedDirections = map[string]struct{}{
	DirectionInbound:  {},
	DirectionOutbound: {},
}

var allowedIOStatus = map[string]struct{}{
	"success": {},
	"failed":  {},
	"timeout": {},
	"retry":   {},
}

type IOAccessLog struct {
	SchemaVersion     string `json:"schemaVersion"`
	Service           string `json:"service"`
	Timestamp         string `json:"timestamp"`
	Origin            string `json:"origin"`
	Direction         string `json:"direction"`
	Endpoint          string `json:"endpoint"`
	SourceID          string `json:"sourceId"`
	TraceID           string `json:"traceId"`
	RequestID         string `json:"requestId"`
	SessionID         string `json:"sessionId"`
	Src               string `json:"src"`
	UserID            string `json:"userId,omitempty"`
	SubAccountID      string `json:"subAccountId,omitempty"`
	PageID            string `json:"pageId,omitempty"`
	DevicePlatform    string `json:"devicePlatform,omitempty"`
	AppVersion        string `json:"appVersion,omitempty"`
	ServiceName       string `json:"serviceName,omitempty"`
	ServiceInstanceID string `json:"serviceInstanceId,omitempty"`
	Status            string `json:"status"`
	DurationMs        int64  `json:"durationMs"`
	ErrorCode         string `json:"errorCode,omitempty"`
	ErrorLocation     string `json:"errorLocation,omitempty"`
	ErrorContext      string `json:"errorContext,omitempty"`
	MessageSize       int64  `json:"messageSize"`
}

func (l IOAccessLog) Validate() error {
	if l.SchemaVersion == "" || l.Service == "" || l.Timestamp == "" || l.Endpoint == "" {
		return fmt.Errorf("missing required base fields")
	}
	if _, ok := allowedOrigins[l.Origin]; !ok {
		return fmt.Errorf("invalid origin: %s", l.Origin)
	}
	if _, ok := allowedDirections[l.Direction]; !ok {
		return fmt.Errorf("invalid direction: %s", l.Direction)
	}
	if l.SourceID == "" || l.TraceID == "" || l.RequestID == "" || l.SessionID == "" || l.Src == "" {
		return fmt.Errorf("missing required trace/source fields")
	}
	if _, ok := allowedIOStatus[l.Status]; !ok {
		return fmt.Errorf("invalid status: %s", l.Status)
	}
	if l.DurationMs < 0 || l.MessageSize < 0 {
		return fmt.Errorf("durationMs/messageSize must be >= 0")
	}
	if strings.HasPrefix(l.Origin, "app.") {
		if l.DevicePlatform == "" || l.AppVersion == "" || l.PageID == "" {
			return fmt.Errorf("app origin requires devicePlatform/appVersion/pageId")
		}
	}
	if strings.HasPrefix(l.Origin, "service.") || strings.HasPrefix(l.Origin, "job.") || strings.HasPrefix(l.Origin, "cron.") {
		if l.ServiceName == "" || l.ServiceInstanceID == "" {
			return fmt.Errorf("service/job/cron origin requires serviceName/serviceInstanceId")
		}
	}
	return nil
}
