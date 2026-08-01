package runruntime

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

type ChildExecutionKind string

const (
	ChildTool     ChildExecutionKind = "tool"
	ChildSubagent ChildExecutionKind = "subagent"
)

type ChildExecution interface {
	ExecutionID() string
	Kind() ChildExecutionKind
	Cancel(context.Context) error
	AwaitStopped(context.Context) error
}

// ChildExecutionRegistry must fence registration and return the active child
// snapshot atomically. Once fenced, no tool or Subagent may start a new side
// effect for the Run.
type ChildExecutionRegistry interface {
	FenceAndList(context.Context, string) ([]ChildExecution, error)
}

type CancellationCoordinator struct {
	children       ChildExecutionRegistry
	cleanupTimeout time.Duration
}

func NewCancellationCoordinator(
	children ChildExecutionRegistry,
	cleanupTimeout time.Duration,
) *CancellationCoordinator {
	if children == nil || cleanupTimeout <= 0 {
		panic("assistant run cancellation dependencies are required")
	}
	return &CancellationCoordinator{children: children, cleanupTimeout: cleanupTimeout}
}

func (c *CancellationCoordinator) Cancel(
	ctx context.Context,
	run *Run,
	reason string,
	now time.Time,
) error {
	if run == nil {
		return ErrInvalidRun
	}
	if run.State == generated.AssistantRunStateCancelled {
		return nil
	}
	if terminalState(run.State) {
		return ErrInvalidTransition
	}
	cleanupCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), c.cleanupTimeout)
	defer cancel()
	children, err := c.children.FenceAndList(cleanupCtx, run.RunID)
	if err != nil {
		return fmt.Errorf("fence assistant run children: %w", err)
	}
	if err := cancelChildren(cleanupCtx, children); err != nil {
		return err
	}
	if err := awaitChildren(cleanupCtx, children); err != nil {
		return err
	}
	run.CancelActiveWork(reason, now)
	return run.Transition(generated.AssistantRunStateCancelled, reason, now)
}

func cancelChildren(ctx context.Context, children []ChildExecution) error {
	return parallelChildren(children, func(child ChildExecution) error {
		if err := child.Cancel(ctx); err != nil {
			return fmt.Errorf("cancel %s %s: %w", child.Kind(), child.ExecutionID(), err)
		}
		return nil
	})
}

func awaitChildren(ctx context.Context, children []ChildExecution) error {
	return parallelChildren(children, func(child ChildExecution) error {
		if err := child.AwaitStopped(ctx); err != nil {
			return fmt.Errorf("await %s %s: %w", child.Kind(), child.ExecutionID(), err)
		}
		return nil
	})
}

func parallelChildren(
	children []ChildExecution,
	action func(ChildExecution) error,
) error {
	var wait sync.WaitGroup
	failures := make(chan error, len(children))
	for _, child := range children {
		child := child
		if child == nil {
			failures <- errors.New("nil assistant run child execution")
			continue
		}
		wait.Add(1)
		go func() {
			defer wait.Done()
			if err := action(child); err != nil {
				failures <- err
			}
		}()
	}
	wait.Wait()
	close(failures)
	var result []error
	for failure := range failures {
		result = append(result, failure)
	}
	return errors.Join(result...)
}
