package runtimeobservability

import "fmt"

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
	TS                string `json:"ts"`
	Origin            string `json:"-"`
	Direction         string `json:"-"`
	Method            string `json:"method,omitempty"`
	Endpoint          string `json:"route"`
	Trace             string `json:"trace,omitempty"`
	Req               string `json:"req,omitempty"`
	Service           string `json:"-"`
	SourceID          string `json:"-"`
	SessionID         string `json:"-"`
	Src               string `json:"-"`
	UserID            string `json:"-"`
	PersonaID         string `json:"-"`
	PageID            string `json:"-"`
	DevicePlatform    string `json:"-"`
	AppVersion        string `json:"-"`
	ServiceName       string `json:"-"`
	ServiceInstanceID string `json:"-"`
	Status            string `json:"status"`
	DurationMs        int64  `json:"durMs"`
	ErrorCode         string `json:"err,omitempty"`
	ErrorLocation     string `json:"-"`
	ErrorContext      string `json:"-"`
	MessageSize       int64  `json:"-"`
}

func (l IOAccessLog) Validate() error {
	if l.TS == "" || l.Endpoint == "" {
		return fmt.Errorf("missing required access fields")
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
	if _, ok := allowedIOStatus[l.Status]; !ok {
		return fmt.Errorf("invalid status: %s", l.Status)
	}
	if l.DurationMs < 0 {
		return fmt.Errorf("durMs must be >= 0")
	}
	return nil
}
