package runtimeobservability

import "fmt"

type ExceptionIO struct {
	InputKV  map[string]any `json:"inputKv,omitempty"`
	OutputKV map[string]any `json:"outputKv,omitempty"`
}

type ExceptionLog struct {
	TS                string      `json:"ts"`
	Origin            string      `json:"-"`
	Direction         string      `json:"-"`
	Endpoint          string      `json:"-"`
	Trace             string      `json:"trace,omitempty"`
	Req               string      `json:"req,omitempty"`
	Service           string      `json:"-"`
	SourceID          string      `json:"-"`
	SessionID         string      `json:"-"`
	Src               string      `json:"-"`
	UserID            string      `json:"-"`
	PersonaID         string      `json:"-"`
	PageID            string      `json:"-"`
	DevicePlatform    string      `json:"-"`
	AppVersion        string      `json:"-"`
	ServiceName       string      `json:"-"`
	ServiceInstanceID string      `json:"-"`
	ErrorCode         string      `json:"err"`
	ErrorModule       string      `json:"module"`
	ErrorKind         string      `json:"kind"`
	ErrorReason       string      `json:"reason"`
	RuntimeOrigin     string      `json:"runtimeOrigin,omitempty"`
	RuntimeNature     string      `json:"runtimeNature,omitempty"`
	UserMessage       string      `json:"msg"`
	DebugMessage      string      `json:"debug,omitempty"`
	StackHash         string      `json:"stackHash,omitempty"`
	FailurePoint      string      `json:"failurePoint,omitempty"`
	BusinessObject    string      `json:"businessObject,omitempty"`
	FunctionModule    string      `json:"functionModule,omitempty"`
	IO                ExceptionIO `json:"io,omitempty"`
}

func (l ExceptionLog) Validate() error {
	if l.TS == "" {
		return fmt.Errorf("missing required exception time")
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
	if l.ErrorCode == "" || l.ErrorModule == "" || l.ErrorKind == "" || l.ErrorReason == "" || l.UserMessage == "" {
		return fmt.Errorf("missing required exception fields")
	}
	if !errorCodePattern.MatchString(l.ErrorCode) {
		return fmt.Errorf("invalid errorCode format: %s", l.ErrorCode)
	}
	return nil
}
