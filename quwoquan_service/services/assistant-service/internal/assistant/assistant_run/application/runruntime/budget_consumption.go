package runruntime

import (
	"fmt"
	"strings"
	"time"
)

// BudgetConsumption is the Run-owned cumulative usage ledger. Values are
// absolute across the Run, never allocations copied from child Task budgets.
type BudgetConsumption struct {
	ToolCalls int64 `bson:"toolCalls"`
	Tokens    int64 `bson:"tokens"`
	CostUnits int64 `bson:"costUnits"`
}

// BudgetConsumptionReceipt is an idempotent observation emitted at a model or
// tool boundary. Scope is frozen to Run + goal revision + root execution
// attempt; Sequence is monotonic within that scope and Consumption remains the
// absolute Run total across every verifier repair attempt.
type BudgetConsumptionReceipt struct {
	Scope       string
	Sequence    int64
	Consumption BudgetConsumption
}

func budgetConsumptionFromCheckpoint(checkpoint *Checkpoint) BudgetConsumption {
	if checkpoint == nil {
		return BudgetConsumption{}
	}
	return checkpoint.BudgetConsumption
}

func budgetReceiptScope(run Run) string {
	return executionAttemptScope(run)
}

func executionAttemptScope(run Run) string {
	scope := "run:" + strings.TrimSpace(run.RunID) + ":goal:" +
		fmt.Sprint(run.GoalRevision)
	for _, task := range run.TaskGraph.Tasks {
		if task.TaskID == "task_root" && task.Attempt > 1 {
			return scope + ":task:task_root:attempt:" + fmt.Sprint(task.Attempt)
		}
	}
	return scope
}

func (r *Run) RecordBudgetConsumption(
	receipt BudgetConsumptionReceipt,
	now time.Time,
) error {
	if r == nil || terminalState(r.State) ||
		strings.TrimSpace(receipt.Scope) != budgetReceiptScope(*r) ||
		receipt.Sequence <= 0 || !validBudgetConsumption(receipt.Consumption) {
		return ErrInvalidRun
	}
	current := budgetConsumptionFromCheckpoint(r.Checkpoint)
	if r.Checkpoint != nil &&
		strings.TrimSpace(r.Checkpoint.BudgetReceiptScope) == receipt.Scope {
		switch {
		case receipt.Sequence < r.Checkpoint.BudgetReceiptSeq:
			return nil
		case receipt.Sequence == r.Checkpoint.BudgetReceiptSeq:
			if receipt.Consumption == current {
				return nil
			}
			return ErrRevisionConflict
		}
	}
	if receipt.Consumption.ToolCalls < current.ToolCalls ||
		receipt.Consumption.Tokens < current.Tokens ||
		receipt.Consumption.CostUnits < current.CostUnits {
		return ErrRevisionConflict
	}
	if r.Checkpoint == nil {
		if _, err := r.CreateCheckpoint(
			"checkpoint:"+r.RunID+":budget",
			r.DefinitionOfDone.Outcome,
			nil,
			"",
			remainingBudgetFromConsumption(*r, receipt.Consumption),
			now,
		); err != nil {
			return err
		}
	} else if receipt.Consumption == current &&
		r.Checkpoint.BudgetReceiptScope == receipt.Scope &&
		r.Checkpoint.BudgetReceiptSeq == receipt.Sequence {
		return nil
	}
	r.Checkpoint.BudgetConsumption = receipt.Consumption
	r.Checkpoint.BudgetReceiptScope = receipt.Scope
	r.Checkpoint.BudgetReceiptSeq = receipt.Sequence
	r.Checkpoint.RemainingBudget = remainingBudgetFromConsumption(
		*r,
		receipt.Consumption,
	)
	r.touch(now)
	r.Checkpoint.Revision = r.Revision
	return nil
}

func validBudgetConsumption(consumption BudgetConsumption) bool {
	return consumption.ToolCalls >= 0 && consumption.Tokens >= 0 &&
		consumption.CostUnits >= 0
}

func remainingBudgetFromConsumption(
	run Run,
	consumption BudgetConsumption,
) map[string]int64 {
	remaining := map[string]int64{
		"toolCalls": 0,
		"tokens":    0,
		"costUnits": 0,
	}
	for _, task := range run.TaskGraph.Tasks {
		if task.TaskID != "task_root" {
			continue
		}
		remaining["toolCalls"] = nonnegativeBudget(
			int64(task.Budget.MaxToolCalls) - consumption.ToolCalls,
		)
		remaining["tokens"] = nonnegativeBudget(
			task.Budget.MaxTokens - consumption.Tokens,
		)
		remaining["costUnits"] = nonnegativeBudget(
			task.Budget.MaxCostUnits - consumption.CostUnits,
		)
		break
	}
	return remaining
}

func nonnegativeBudget(value int64) int64 {
	if value < 0 {
		return 0
	}
	return value
}
