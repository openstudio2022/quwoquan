package local_contract

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	assistantruntest "quwoquan_service/services/assistant-service/tests/support/assistantrun"
)

func canonicalRunTestOption(
	t *testing.T,
	loop *orchestration.AgentLoop,
) orchestration.AssistantServiceOption {
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
		time.Now,
		nil,
	)
	worker := runruntime.NewDurableWorker(
		runtime,
		runtime,
		orchestration.NewDurableRunExecutorWithPolicyResolver(
			loop,
			func(
				_ context.Context,
				request runruntime.ExecutionRequest,
			) (assistant.AssistantFrozenPolicySelection, error) {
				return testFrozenPolicySelection(
					"assistant-default",
					request.RequestedSkillID,
					request.RequestedDomainID,
				), nil
			},
		),
		"local-contract-canonical-run-worker",
	)
	workerContext, cancelWorker := context.WithCancel(context.Background())
	t.Cleanup(cancelWorker)
	go worker.Run(workerContext)

	return orchestration.WithRunCommandService(commands)
}
