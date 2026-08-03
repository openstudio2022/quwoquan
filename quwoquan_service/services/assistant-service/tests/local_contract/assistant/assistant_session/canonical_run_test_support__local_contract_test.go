package local_contract

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	assistantruntest "quwoquan_service/services/assistant-service/tests/support/assistantrun"
)

func canonicalRunTestOption(
	t *testing.T,
	loop *orchestration.AgentLoop,
) orchestration.AssistantServiceOption {
	t.Helper()
	option, _ := canonicalRunTestRuntime(t, loop)
	return option
}

func canonicalRunTestRuntime(
	t *testing.T,
	loop *orchestration.AgentLoop,
) (orchestration.AssistantServiceOption, *assistantruntest.MemoryRuntime) {
	t.Helper()

	runtime := assistantruntest.NewMemoryRuntime()
	commands := runruntime.NewCommandService(
		runtime,
		runruntime.SessionAuthorizerFunc(func(
			context.Context,
			string,
			string,
		) error {
			return nil
		}),
		testSkillPackageIdentityResolver(),
		runruntime.AllowAllStartAccessPolicy{},
		time.Now,
		nil,
		testRunPolicyResolver(),
	)
	worker := runruntime.NewDurableWorker(
		runtime,
		runtime,
		orchestration.NewDurableRunExecutor(loop),
		"local-contract-canonical-run-worker",
	)
	workerContext, cancelWorker := context.WithCancel(context.Background())
	t.Cleanup(cancelWorker)
	go worker.Run(workerContext)

	return orchestration.WithRunCommandService(commands), runtime
}
