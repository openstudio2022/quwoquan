package runtimeobservability

import (
	"fmt"
	"io"
)

type SinkRouter struct {
	standardSink io.Writer
	errorSink    io.Writer
}

func NewSinkRouter(standardSink io.Writer, errorSink io.Writer) (*SinkRouter, error) {
	if standardSink == nil {
		return nil, fmt.Errorf("standard sink is required")
	}
	if errorSink == nil {
		return nil, fmt.Errorf("error sink is required")
	}
	return &SinkRouter{
		standardSink: standardSink,
		errorSink:    errorSink,
	}, nil
}

func (r *SinkRouter) WriteStandard(payload []byte) error {
	_, err := r.standardSink.Write(payload)
	return err
}

func (r *SinkRouter) WriteError(payload []byte) error {
	_, err := r.errorSink.Write(payload)
	return err
}

