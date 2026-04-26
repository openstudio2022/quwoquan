package failures

import "strings"

type Location struct {
	BusinessObject   string `json:"businessObject"`
	FunctionModule   string `json:"functionModule"`
	SourceFilePath   string `json:"sourceFilePath,omitempty"`
	SourceLineNumber int    `json:"sourceLineNumber,omitempty"`
	SourceLineText   string `json:"sourceLineText,omitempty"`
}

func UnknownLocation() Location {
	return Location{
		BusinessObject: "unknown",
		FunctionModule: "unknown",
	}
}

func (l Location) Normalized() Location {
	l.BusinessObject = strings.TrimSpace(l.BusinessObject)
	l.FunctionModule = strings.TrimSpace(l.FunctionModule)
	l.SourceFilePath = strings.TrimSpace(l.SourceFilePath)
	l.SourceLineText = strings.TrimSpace(l.SourceLineText)
	if l.BusinessObject == "" {
		l.BusinessObject = "unknown"
	}
	if l.FunctionModule == "" {
		l.FunctionModule = "unknown"
	}
	return l
}
