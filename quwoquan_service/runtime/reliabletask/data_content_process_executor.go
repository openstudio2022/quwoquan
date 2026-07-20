package reliabletask

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os/exec"
	"strings"
)

const defaultDataContentProcessOutputBytes int64 = 1024 * 1024

// DataContentProcessExecutor is the process boundary between the Go
// Mongo+Redis fleet and the Python qwq-data object worker. The command is
// selected by the composition root; task payloads can never alter it.
type DataContentProcessExecutor struct {
	Command        []string
	WorkDir        string
	Environment    []string
	MaxOutputBytes int64
}

func (e DataContentProcessExecutor) ExecuteDataContentObject(
	ctx context.Context,
	item DataContentWorkItem,
) (DataContentExecutionResult, error) {
	if len(e.Command) == 0 || strings.TrimSpace(e.Command[0]) == "" {
		return DataContentExecutionResult{}, fmt.Errorf(
			"reliabletask data process executor requires command",
		)
	}
	input, err := json.Marshal(dataContentProcessRequest{
		Schema: "quwoquan.data_content_worker_request",
		Item: dataContentProcessWorkItem{
			RuntimeTaskID:  item.RuntimeTaskID,
			JobID:          item.JobID,
			ExecutionID:    item.ExecutionID,
			Ref:            item.Ref,
			Stage:          item.Stage,
			PartitionKey:   item.PartitionKey,
			EntityRef:      item.EntityRef,
			Carrier:        item.Carrier,
			SourceRevision: item.SourceRevision,
			IdempotencyKey: item.IdempotencyKey,
		},
	})
	if err != nil {
		return DataContentExecutionResult{}, fmt.Errorf(
			"reliabletask data process request encode: %w",
			err,
		)
	}
	command := exec.CommandContext(ctx, e.Command[0], e.Command[1:]...)
	command.Dir = strings.TrimSpace(e.WorkDir)
	if e.Environment != nil {
		command.Env = append([]string(nil), e.Environment...)
	}
	command.Stdin = bytes.NewReader(append(input, '\n'))
	limit := e.MaxOutputBytes
	if limit <= 0 {
		limit = defaultDataContentProcessOutputBytes
	}
	stdout := &dataContentLimitedBuffer{remaining: limit}
	stderr := &dataContentLimitedBuffer{remaining: limit}
	command.Stdout = stdout
	command.Stderr = stderr
	if err := command.Run(); err != nil {
		if ctxErr := ctx.Err(); ctxErr != nil {
			return DataContentExecutionResult{}, ctxErr
		}
		return DataContentExecutionResult{}, fmt.Errorf(
			"reliabletask data process worker failed: %w",
			err,
		)
	}
	if stdout.exceeded || stderr.exceeded {
		return DataContentExecutionResult{}, fmt.Errorf(
			"reliabletask data process worker exceeded output budget",
		)
	}
	decoder := json.NewDecoder(bytes.NewReader(stdout.Bytes()))
	decoder.DisallowUnknownFields()
	var response dataContentProcessResponse
	if err := decoder.Decode(&response); err != nil {
		return DataContentExecutionResult{}, fmt.Errorf(
			"reliabletask data process response decode: %w",
			err,
		)
	}
	if err := ensureDataContentJSONEOF(decoder); err != nil {
		return DataContentExecutionResult{}, err
	}
	if response.Schema != "quwoquan.data_content_worker_response" {
		return DataContentExecutionResult{}, fmt.Errorf(
			"reliabletask data process response schema is invalid",
		)
	}
	return response.Result, nil
}

type dataContentProcessRequest struct {
	Schema string                     `json:"schema"`
	Item   dataContentProcessWorkItem `json:"item"`
}

type dataContentProcessWorkItem struct {
	RuntimeTaskID  string `json:"runtimeTaskId"`
	JobID          string `json:"jobId"`
	ExecutionID    string `json:"executionId"`
	Ref            string `json:"ref"`
	Stage          string `json:"stage"`
	PartitionKey   string `json:"partitionKey"`
	EntityRef      string `json:"entityRef"`
	Carrier        string `json:"carrier"`
	SourceRevision string `json:"sourceRevision"`
	IdempotencyKey string `json:"idempotencyKey"`
}

type dataContentProcessResponse struct {
	Schema string                     `json:"schema"`
	Result DataContentExecutionResult `json:"result"`
}

type dataContentLimitedBuffer struct {
	buffer    bytes.Buffer
	remaining int64
	exceeded  bool
}

func (b *dataContentLimitedBuffer) Write(value []byte) (int, error) {
	original := len(value)
	if int64(len(value)) > b.remaining {
		value = value[:max(0, int(b.remaining))]
		b.exceeded = true
	}
	if len(value) > 0 {
		_, _ = b.buffer.Write(value)
		b.remaining -= int64(len(value))
	}
	return original, nil
}

func (b *dataContentLimitedBuffer) Bytes() []byte {
	return b.buffer.Bytes()
}

func ensureDataContentJSONEOF(decoder *json.Decoder) error {
	var trailing any
	if err := decoder.Decode(&trailing); err == io.EOF {
		return nil
	} else if err != nil {
		return fmt.Errorf("reliabletask data process response trailing data: %w", err)
	}
	return fmt.Errorf("reliabletask data process response contains multiple values")
}
