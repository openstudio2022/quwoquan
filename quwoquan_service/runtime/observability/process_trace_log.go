package runtimeobservability

import (
	"fmt"
	"strings"
)

const (
	TraceLogLevelOff   = "off"
	TraceLogLevelInfo  = "info"
	TraceLogLevelDebug = "debug"
)

var allowedTraceLevels = map[string]struct{}{
	TraceLogLevelInfo:  {},
	TraceLogLevelDebug: {},
}

type ProcessTraceIO struct {
	InputKV  map[string]any `json:"inputKv,omitempty"`
	OutputKV map[string]any `json:"outputKv,omitempty"`
}

type ProcessTraceLog struct {
	SchemaVersion     string         `json:"schemaVersion"`
	Service           string         `json:"service"`
	Timestamp         string         `json:"timestamp"`
	Origin            string         `json:"origin"`
	Direction         string         `json:"direction"`
	Endpoint          string         `json:"endpoint"`
	SourceID          string         `json:"sourceId"`
	TraceID           string         `json:"traceId"`
	RequestID         string         `json:"requestId"`
	SessionID         string         `json:"sessionId"`
	Src               string         `json:"src"`
	UserID            string         `json:"userId,omitempty"`
	SubAccountID      string         `json:"subAccountId,omitempty"`
	PageID            string         `json:"pageId,omitempty"`
	DevicePlatform    string         `json:"devicePlatform,omitempty"`
	AppVersion        string         `json:"appVersion,omitempty"`
	ServiceName       string         `json:"serviceName,omitempty"`
	ServiceInstanceID string         `json:"serviceInstanceId,omitempty"`
	Step              string         `json:"step"`
	Event             string         `json:"event"`
	Result            string         `json:"result"`
	Level             string         `json:"level"`
	IO                ProcessTraceIO `json:"io,omitempty"`
}

func (l ProcessTraceLog) Validate() error {
	if l.SchemaVersion == "" || l.Service == "" || l.Timestamp == "" || l.Endpoint == "" {
		return fmt.Errorf("missing required base fields")
	}
	if _, ok := allowedOrigins[l.Origin]; !ok {
		return fmt.Errorf("invalid origin: %s", l.Origin)
	}
	if _, ok := allowedDirections[l.Direction]; !ok {
		return fmt.Errorf("invalid direction: %s", l.Direction)
	}
	if _, ok := allowedTraceLevels[l.Level]; !ok {
		return fmt.Errorf("invalid level: %s", l.Level)
	}
	if l.SourceID == "" || l.TraceID == "" || l.RequestID == "" || l.SessionID == "" || l.Src == "" {
		return fmt.Errorf("missing required trace/source fields")
	}
	if l.Step == "" || l.Event == "" || l.Result == "" {
		return fmt.Errorf("missing required process fields")
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
