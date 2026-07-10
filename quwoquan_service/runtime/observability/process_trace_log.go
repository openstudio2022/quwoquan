package runtimeobservability

import "fmt"

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
	TS                string         `json:"ts"`
	Origin            string         `json:"-"`
	Direction         string         `json:"-"`
	Endpoint          string         `json:"-"`
	Trace             string         `json:"trace,omitempty"`
	Req               string         `json:"req,omitempty"`
	Service           string         `json:"-"`
	SourceID          string         `json:"-"`
	SessionID         string         `json:"-"`
	Src               string         `json:"-"`
	UserID            string         `json:"-"`
	SubAccountID      string         `json:"-"`
	PageID            string         `json:"-"`
	DevicePlatform    string         `json:"-"`
	AppVersion        string         `json:"-"`
	ServiceName       string         `json:"-"`
	ServiceInstanceID string         `json:"-"`
	Step              string         `json:"step"`
	Event             string         `json:"event"`
	Result            string         `json:"result"`
	Level             string         `json:"level"`
	IO                ProcessTraceIO `json:"io,omitempty"`
}

func (l ProcessTraceLog) Validate() error {
	if l.TS == "" {
		return fmt.Errorf("missing required runtime time")
	}
	if l.Origin != "" {
		if _, ok := allowedOrigins[l.Origin]; !ok {
			return fmt.Errorf("invalid origin: %s", l.Origin)
		}
	}
	if l.Direction != "" {
		if _, ok := allowedDirections[l.Direction]; !ok {
			return fmt.Errorf("invalid direction: %s", l.Direction)
		}
	}
	if _, ok := allowedTraceLevels[l.Level]; !ok {
		return fmt.Errorf("invalid level: %s", l.Level)
	}
	if l.Step == "" || l.Event == "" || l.Result == "" {
		return fmt.Errorf("missing required process fields")
	}
	return nil
}
