package runtimeobservability

import (
	"fmt"
	"strings"
)

type ExceptionIO struct {
	InputKV  map[string]any `json:"inputKv,omitempty"`
	OutputKV map[string]any `json:"outputKv,omitempty"`
}

type ExceptionLog struct {
	SchemaVersion     string      `json:"schemaVersion"`
	Service           string      `json:"service"`
	Timestamp         string      `json:"timestamp"`
	Origin            string      `json:"origin"`
	Direction         string      `json:"direction"`
	Endpoint          string      `json:"endpoint"`
	SourceID          string      `json:"sourceId"`
	TraceID           string      `json:"traceId"`
	RequestID         string      `json:"requestId"`
	SessionID         string      `json:"sessionId"`
	Src               string      `json:"src"`
	UserID            string      `json:"userId,omitempty"`
	SubAccountID      string      `json:"subAccountId,omitempty"`
	PageID            string      `json:"pageId,omitempty"`
	DevicePlatform    string      `json:"devicePlatform,omitempty"`
	AppVersion        string      `json:"appVersion,omitempty"`
	ServiceName       string      `json:"serviceName,omitempty"`
	ServiceInstanceID string      `json:"serviceInstanceId,omitempty"`
	ErrorCode         string      `json:"errorCode"`
	ErrorModule       string      `json:"errorModule"`
	ErrorKind         string      `json:"errorKind"`
	ErrorReason       string      `json:"errorReason"`
	RuntimeOrigin     string      `json:"runtimeOrigin,omitempty"`
	RuntimeNature     string      `json:"runtimeNature,omitempty"`
	UserMessage       string      `json:"userMessage"`
	DebugMessage      string      `json:"debugMessage,omitempty"`
	StackHash         string      `json:"stackHash,omitempty"`
	FailurePoint      string      `json:"failurePoint,omitempty"`
	BusinessObject    string      `json:"businessObject,omitempty"`
	FunctionModule    string      `json:"functionModule,omitempty"`
	IO                ExceptionIO `json:"io,omitempty"`
}

func (l ExceptionLog) Validate() error {
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
	if l.ErrorCode == "" || l.ErrorModule == "" || l.ErrorKind == "" || l.ErrorReason == "" || l.UserMessage == "" {
		return fmt.Errorf("missing required exception fields")
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
	if !errorCodePattern.MatchString(l.ErrorCode) {
		return fmt.Errorf("invalid errorCode format: %s", l.ErrorCode)
	}
	return nil
}
