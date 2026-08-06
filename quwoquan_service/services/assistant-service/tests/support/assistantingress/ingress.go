// Package assistantingress composes the assistant-service inbound HTTP
// adapters that a cross-object flow test spans. AssistantSession and
// AssistantRun own separate adapters; this shared launcher only reproduces the
// cmd/api composition order so behaviour tests observe the same routing table
// as production.
package assistantingress

import (
	"net/http"

	runhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/adapters/inbound/http"
	runapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	sessionhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
)

type config struct {
	runCommands *runruntime.CommandService
	runOptions  []runhttp.HandlerOption
}

type Option func(*config)

// WithRunCommandService overrides the AssistantRun command service; by default
// the composition reuses the one already bound to the session service.
func WithRunCommandService(commands *runruntime.CommandService) Option {
	return func(cfg *config) { cfg.runCommands = commands }
}

func WithRunPreferenceSnapshots(reader runapplication.PreferenceSnapshotReader) Option {
	return func(cfg *config) {
		cfg.runOptions = append(
			cfg.runOptions,
			runhttp.WithPreferenceSnapshots(reader),
		)
	}
}

func WithRunContextResolver(resolver *runapplication.ContextResolver) Option {
	return func(cfg *config) {
		cfg.runOptions = append(
			cfg.runOptions,
			runhttp.WithContextResolver(resolver),
		)
	}
}

func Routes(
	service *orchestration.AssistantService,
	options ...Option,
) http.Handler {
	cfg := &config{runCommands: service.RunCommandService()}
	for _, option := range options {
		option(cfg)
	}
	mux := http.NewServeMux()
	if cfg.runCommands != nil {
		runhttp.NewHandler(cfg.runCommands, cfg.runOptions...).
			RegisterRoutes(mux)
	}
	mux.Handle("/", sessionhttp.NewHandler(service).Routes())
	return mux
}
