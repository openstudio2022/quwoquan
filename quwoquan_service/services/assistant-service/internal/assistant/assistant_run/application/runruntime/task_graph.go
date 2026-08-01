package runruntime

import (
	"fmt"
	"strings"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

func NewTaskGraph(tasks []TaskNode) (TaskGraph, error) {
	graph := TaskGraph{GraphRevision: 1, Tasks: cloneTasks(tasks)}
	for index := range graph.Tasks {
		if graph.Tasks[index].Status == "" {
			graph.Tasks[index].Status = generated.AssistantTaskStatusPending
		}
	}
	if err := validateTaskGraph(graph.Tasks); err != nil {
		return TaskGraph{}, err
	}
	graph.refreshReadyTasks()
	return graph, nil
}

func (g *TaskGraph) Start(taskID string) error {
	index := g.taskIndex(taskID)
	if index < 0 || g.Tasks[index].Status != generated.AssistantTaskStatusReady {
		return ErrTaskNotReady
	}
	g.Tasks[index].Status = generated.AssistantTaskStatusRunning
	g.Tasks[index].Attempt++
	g.GraphRevision++
	return nil
}

func (g *TaskGraph) Complete(
	taskID string,
	artifactRefs []string,
	verification TaskVerification,
) error {
	index := g.taskIndex(taskID)
	if index < 0 || g.Tasks[index].Status != generated.AssistantTaskStatusRunning {
		return ErrTaskNotReady
	}
	if len(verification.Requirements) > 0 && !verification.Passed {
		return fmt.Errorf("%w: task verification did not pass", ErrCompletionRejected)
	}
	g.Tasks[index].Status = generated.AssistantTaskStatusCompleted
	g.Tasks[index].ArtifactRefs = append([]string{}, artifactRefs...)
	g.Tasks[index].Verification = cloneVerification(verification)
	g.GraphRevision++
	g.refreshReadyTasks()
	return nil
}

func (g *TaskGraph) Fail(taskID, reason string, retryable bool) error {
	index := g.taskIndex(taskID)
	if index < 0 || g.Tasks[index].Status != generated.AssistantTaskStatusRunning {
		return ErrTaskNotReady
	}
	if retryable {
		g.Tasks[index].Status = generated.AssistantTaskStatusReady
	} else {
		g.Tasks[index].Status = generated.AssistantTaskStatusFailed
	}
	g.Tasks[index].BlockReason = strings.TrimSpace(reason)
	g.GraphRevision++
	return nil
}

func (g TaskGraph) AllCompleted() bool {
	if len(g.Tasks) == 0 {
		return false
	}
	for _, task := range g.Tasks {
		if task.Status != generated.AssistantTaskStatusCompleted {
			return false
		}
	}
	return true
}

func (g TaskGraph) taskIndex(taskID string) int {
	for index := range g.Tasks {
		if g.Tasks[index].TaskID == taskID {
			return index
		}
	}
	return -1
}

func (g *TaskGraph) refreshReadyTasks() {
	completed := make(map[string]bool, len(g.Tasks))
	for _, task := range g.Tasks {
		completed[task.TaskID] = task.Status == generated.AssistantTaskStatusCompleted
	}
	for index := range g.Tasks {
		if g.Tasks[index].Status != generated.AssistantTaskStatusPending {
			continue
		}
		ready := true
		for _, dependency := range g.Tasks[index].Dependencies {
			if !completed[dependency] {
				ready = false
				break
			}
		}
		if ready {
			g.Tasks[index].Status = generated.AssistantTaskStatusReady
		}
	}
}

func validateTaskGraph(tasks []TaskNode) error {
	if len(tasks) == 0 {
		return fmt.Errorf("%w: no tasks", ErrInvalidTaskGraph)
	}
	indices := make(map[string]int, len(tasks))
	for index, task := range tasks {
		if strings.TrimSpace(task.TaskID) == "" || strings.TrimSpace(task.Goal) == "" {
			return fmt.Errorf("%w: task id and goal are required", ErrInvalidTaskGraph)
		}
		if _, exists := indices[task.TaskID]; exists {
			return fmt.Errorf("%w: duplicate task %s", ErrInvalidTaskGraph, task.TaskID)
		}
		indices[task.TaskID] = index
		if task.Status != "" && task.Status != generated.AssistantTaskStatusPending {
			return fmt.Errorf("%w: new task %s is not pending", ErrInvalidTaskGraph, task.TaskID)
		}
	}
	for _, task := range tasks {
		for _, dependency := range task.Dependencies {
			if _, ok := indices[dependency]; !ok || dependency == task.TaskID {
				return fmt.Errorf("%w: bad dependency %s", ErrInvalidTaskGraph, dependency)
			}
		}
	}
	visiting := make(map[string]bool, len(tasks))
	visited := make(map[string]bool, len(tasks))
	var visit func(string) error
	visit = func(taskID string) error {
		if visiting[taskID] {
			return fmt.Errorf("%w: dependency cycle", ErrInvalidTaskGraph)
		}
		if visited[taskID] {
			return nil
		}
		visiting[taskID] = true
		for _, dependency := range tasks[indices[taskID]].Dependencies {
			if err := visit(dependency); err != nil {
				return err
			}
		}
		visiting[taskID] = false
		visited[taskID] = true
		return nil
	}
	for _, task := range tasks {
		if err := visit(task.TaskID); err != nil {
			return err
		}
	}
	return nil
}

func cloneTasks(tasks []TaskNode) []TaskNode {
	result := make([]TaskNode, len(tasks))
	for index, task := range tasks {
		result[index] = task
		result[index].Dependencies = append([]string{}, task.Dependencies...)
		result[index].ArtifactRefs = append([]string{}, task.ArtifactRefs...)
		result[index].Verification = cloneVerification(task.Verification)
	}
	return result
}

func cloneVerification(value TaskVerification) TaskVerification {
	value.Requirements = append([]string{}, value.Requirements...)
	value.EvidenceRefs = append([]string{}, value.EvidenceRefs...)
	return value
}
