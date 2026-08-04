package local_contract

import (
	"context"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	runorchestration "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	sessionorchestration "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	assistantruntest "quwoquan_service/services/assistant-service/tests/support/assistantrun"
)

func durableTestReasoningPolicy(
	t *testing.T,
) runruntime.ReasoningProfileConfig {
	t.Helper()
	catalog, err := runruntime.DefaultReasoningProfileCatalog()
	if err != nil {
		t.Fatal(err)
	}
	policy, err := catalog.Resolve(generated.AssistantReasoningProfileBalanced)
	if err != nil {
		t.Fatal(err)
	}
	return policy
}

func durableTestModelCapabilities() runorchestration.ModelExecutionCapabilities {
	return runorchestration.ModelExecutionCapabilities{
		ToolCalling:     true,
		ParallelTools:   true,
		ReasoningEffort: true,
	}
}

func canonicalRunTestOption(
	t *testing.T,
	loop *runorchestration.AgentLoop,
) sessionorchestration.AssistantServiceOption {
	t.Helper()
	option, _ := canonicalRunTestRuntime(t, loop)
	return option
}

func canonicalRunTestRuntime(
	t *testing.T,
	loop *runorchestration.AgentLoop,
) (sessionorchestration.AssistantServiceOption, *assistantruntest.MemoryRuntime) {
	t.Helper()

	runtime := assistantruntest.NewMemoryRuntime()
	commands := runruntime.NewCommandService(
		runtime,
		runruntime.SessionResolverFunc(func(
			context.Context,
			string,
			string,
		) (runruntime.SessionContinuity, error) {
			return runruntime.SessionContinuity{}, nil
		}),
		testSkillPackageIdentityResolver(),
		runruntime.AllowAllStartAccessPolicy{},
		time.Now,
		nil,
		runruntime.WithPolicyResolver(testRunPolicyResolver()),
	)
	worker := runruntime.NewDurableWorker(
		runtime,
		runtime,
		runorchestration.NewDurableRunExecutor(loop),
		"local-contract-canonical-run-worker",
	)
	workerContext, cancelWorker := context.WithCancel(context.Background())
	t.Cleanup(cancelWorker)
	go worker.Run(workerContext)

	return sessionorchestration.WithRunCommandService(commands), runtime
}
