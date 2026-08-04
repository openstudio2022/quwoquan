package orchestration

import (
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

// executionTaskTracker derives the durable DAG from the same public process
// events that describe actual AgentLoop work. It is a projection of model
// decisions, not a second planner: AssistantRun validates and persists every
// proposed node before its RunItem can start.
type executionTaskTracker struct {
	request runruntime.ExecutionRequest
	tasks   map[string]trackedExecutionTask
	order   []string
}

type trackedExecutionTask struct {
	definition *runruntime.ExecutionTaskUpdate
	status     generated.AssistantTaskStatus
}

func newExecutionTaskTracker(
	request runruntime.ExecutionRequest,
) *executionTaskTracker {
	tracker := &executionTaskTracker{
		request: request,
		tasks:   make(map[string]trackedExecutionTask, len(request.TaskGraph.Tasks)),
	}
	for _, task := range request.TaskGraph.Tasks {
		if task.TaskID == "task_root" {
			continue
		}
		tracker.order = append(tracker.order, task.TaskID)
		tracker.tasks[task.TaskID] = trackedExecutionTask{
			definition: &runruntime.ExecutionTaskUpdate{
				Goal:         task.Goal,
				Dependencies: append([]string{}, task.Dependencies...),
				OwnerAgent:   task.OwnerAgent,
				Budget:       task.Budget,
			},
			status: task.Status,
		}
	}
	return tracker
}

func (t *executionTaskTracker) taskForProcess(
	process map[string]any,
) (string, *runruntime.ExecutionTaskUpdate) {
	processID := strings.TrimSpace(stringValue(process["processId"]))
	if t == nil || processID == "" {
		return "task_root", nil
	}
	taskID := t.request.IdempotencyPrefix + ":task:" + processID
	if tracked, exists := t.tasks[taskID]; exists {
		return taskID, cloneExecutionTaskUpdate(tracked.definition)
	}
	dependencies := t.completedFrontier()
	definition := t.taskUpdate(process, dependencies)
	t.tasks[taskID] = trackedExecutionTask{
		definition: cloneExecutionTaskUpdate(definition),
		status:     generated.AssistantTaskStatusPending,
	}
	t.order = append(t.order, taskID)
	return taskID, definition
}

func (t *executionTaskTracker) taskUpdate(
	process map[string]any,
	dependencies []string,
) *runruntime.ExecutionTaskUpdate {
	goal := boundedProcessSummary(process)
	if goal == "" {
		goal = "执行助手任务"
	}
	return &runruntime.ExecutionTaskUpdate{
		Goal:         goal,
		Dependencies: append([]string{}, dependencies...),
		OwnerAgent:   processOwnerAgent(process),
		Budget:       executionProcessBudget(t.request, process),
	}
}

func (t *executionTaskTracker) mark(
	taskID string,
	status generated.AssistantTaskStatus,
) {
	if t == nil || taskID == "task_root" {
		return
	}
	tracked, exists := t.tasks[taskID]
	if !exists {
		return
	}
	tracked.status = status
	t.tasks[taskID] = tracked
}

// completedFrontier returns completed leaf tasks only. Running tasks do not
// consume their dependencies, allowing sibling Subagents that are announced
// before parallel execution to share the same predecessor frontier.
func (t *executionTaskTracker) completedFrontier() []string {
	completed := make(map[string]bool, len(t.tasks))
	consumed := make(map[string]bool, len(t.tasks))
	for taskID, task := range t.tasks {
		if task.status != generated.AssistantTaskStatusCompleted {
			continue
		}
		completed[taskID] = true
		for _, dependency := range task.definition.Dependencies {
			consumed[dependency] = true
		}
	}
	frontier := make([]string, 0, len(completed))
	for _, taskID := range t.order {
		if completed[taskID] && !consumed[taskID] {
			frontier = append(frontier, taskID)
		}
	}
	return frontier
}

func cloneExecutionTaskUpdate(
	value *runruntime.ExecutionTaskUpdate,
) *runruntime.ExecutionTaskUpdate {
	if value == nil {
		return nil
	}
	cloned := *value
	cloned.Dependencies = append([]string{}, value.Dependencies...)
	return &cloned
}

func processOwnerAgent(process map[string]any) string {
	if processItemKind(process) == generated.AssistantRunItemKindSubagent {
		if skillID := strings.TrimSpace(stringValue(process["skillId"])); skillID != "" {
			return "subagent:" + skillID
		}
		return "subagent"
	}
	return "manager"
}

func executionProcessBudget(
	request runruntime.ExecutionRequest,
	process map[string]any,
) runruntime.TaskBudget {
	deadline := time.Time{}
	if !request.CreatedAt.IsZero() && request.ReasoningPolicy.Budget.MaxDuration > 0 {
		deadline = request.CreatedAt.UTC().Add(
			request.ReasoningPolicy.Budget.MaxDuration,
		)
	}
	budget := runruntime.TaskBudget{Deadline: deadline}
	switch processItemKind(process) {
	case generated.AssistantRunItemKindToolUse:
		budget.MaxToolCalls = 1
	case generated.AssistantRunItemKindSubagent:
		divisor := request.ReasoningPolicy.Budget.MaxSubagents
		if divisor <= 0 {
			divisor = 1
		}
		budget.MaxToolCalls = request.ReasoningPolicy.Budget.MaxToolCalls / divisor
		budget.MaxTokens = request.ReasoningPolicy.Budget.MaxTokens / int64(divisor)
		budget.MaxCostUnits = request.ReasoningPolicy.Budget.MaxCostUnits / int64(divisor)
	}
	return budget
}
