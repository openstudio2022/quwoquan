package failures

type ErrorResponse struct {
	Code         string   `json:"code"`
	Origin       Origin   `json:"origin"`
	Kind         Kind     `json:"kind"`
	Nature       Nature   `json:"nature"`
	UserMessage  string   `json:"userMessage,omitempty"`
	DebugMessage string   `json:"debugMessage,omitempty"`
	RequestID    string   `json:"requestId,omitempty"`
	TraceID      string   `json:"traceId,omitempty"`
	Location     Location `json:"location"`
	Context      Context  `json:"context"`
}

type ResponseOptions struct {
	RequestID    string
	TraceID      string
	UserMessage  string
	DebugMessage string
	IncludeDebug bool
}

func ToResponse(f FailureBase, opts ResponseOptions) ErrorResponse {
	failure := Failure{
		Code:     f.RuntimeCode(),
		Origin:   f.RuntimeOrigin(),
		Kind:     f.RuntimeKind(),
		Nature:   f.RuntimeNature(),
		Location: f.RuntimeLocation(),
		Context:  f.RuntimeContext(),
	}.Normalized()
	debugMessage := "debug_message_redacted"
	if opts.IncludeDebug && opts.DebugMessage != "" {
		debugMessage = opts.DebugMessage
	}
	return ErrorResponse{
		Code:         failure.Code,
		Origin:       failure.Origin,
		Kind:         failure.Kind,
		Nature:       failure.Nature,
		UserMessage:  opts.UserMessage,
		DebugMessage: debugMessage,
		RequestID:    opts.RequestID,
		TraceID:      opts.TraceID,
		Location:     failure.Location,
		Context:      failure.Context,
	}
}
