// Command seed performs an explicit one-time Assistant environment preseed.
// It is intentionally separate from cmd/api: only beta/gamma operators invoke
// it, and the production API image neither builds nor runs this command.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/environmentseed"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/runtimeconfig"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/runtimewiring"
	learningprojection "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/projection"
	preferenceports "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference_fact/domain/ports"
	preferencepersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference_fact/infrastructure/persistence"
)

const assistantServiceName = "assistant-service"

type commandOptions struct {
	Environment   string
	ConfigRoot    string
	ConfigVersion string
	Refs          []string
	ReportPath    string
	Timeout       time.Duration
}

func main() {
	options, err := parseCommandOptions(os.Args[1:], os.Getenv)
	if err != nil {
		log.Printf("assistant environment seed options invalid: %v", err)
		os.Exit(2)
	}
	if err := run(context.Background(), options); err != nil {
		log.Printf("assistant environment seed failed: %v", err)
		os.Exit(1)
	}
}

func parseCommandOptions(args []string, getenv func(string) string) (commandOptions, error) {
	flags := flag.NewFlagSet("assistant-seed", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	environment := flags.String("env", strings.TrimSpace(getenv("APP_ENV")), "target environment: beta|gamma")
	configRoot := flags.String("config-root", strings.TrimSpace(getenv("CONFIG_ROOT")), "runtime config root")
	configVersion := flags.String("config-version", strings.TrimSpace(getenv("CONFIG_VERSION")), "optional runtime config release version")
	refsCSV := flags.String("refs", strings.TrimSpace(getenv("ASSISTANT_SEED_REFS")), "comma-separated manifest-declared seed refs")
	reportPath := flags.String("report", strings.TrimSpace(getenv("ASSISTANT_SEED_REPORT")), "optional JSON report path")
	timeoutSeconds := flags.Int("timeout-seconds", seedTimeoutSeconds(getenv("ASSISTANT_SEED_TIMEOUT_SECONDS")), "dependency and seed timeout")
	if err := flags.Parse(args); err != nil {
		return commandOptions{}, err
	}
	if flags.NArg() != 0 {
		return commandOptions{}, fmt.Errorf("unexpected positional arguments: %s", strings.Join(flags.Args(), " "))
	}
	env := strings.TrimSpace(*environment)
	if env != "beta" && env != "gamma" {
		return commandOptions{}, fmt.Errorf("--env must be beta or gamma; alpha uses contract mock and prod forbids fixture seed")
	}
	if *timeoutSeconds <= 0 {
		return commandOptions{}, fmt.Errorf("--timeout-seconds must be positive")
	}
	return commandOptions{
		Environment:   env,
		ConfigRoot:    strings.TrimSpace(*configRoot),
		ConfigVersion: strings.TrimSpace(*configVersion),
		Refs:          splitCSV(*refsCSV),
		ReportPath:    strings.TrimSpace(*reportPath),
		Timeout:       time.Duration(*timeoutSeconds) * time.Second,
	}, nil
}

func run(parent context.Context, options commandOptions) error {
	ctx, cancel := context.WithTimeout(parent, options.Timeout)
	defer cancel()

	plan, err := environmentseed.LoadPlan(options.Environment, options.Refs)
	if err != nil {
		return err
	}
	cfg, err := runtimeconfig.LoadRuntimeConfig(
		assistantServiceName,
		options.Environment,
		options.ConfigRoot,
		options.ConfigVersion,
	)
	if err != nil {
		return fmt.Errorf("load assistant runtime config: %w", err)
	}
	if err := runtimeconfig.ApplyEnvOverrides(&cfg); err != nil {
		return fmt.Errorf("apply assistant runtime environment: %w", err)
	}
	if err := runtimewiring.ValidateRuntimeDependenciesConfig(cfg); err != nil {
		return err
	}

	router, err := runtimewiring.BuildRedisRouter(cfg)
	if err != nil {
		return err
	}
	defer router.Close()
	if err := router.PingAll(ctx); err != nil {
		return runtimewiring.NewDependencyError("redis", "connectivity", err)
	}
	deps, err := runtimewiring.OpenPersistentDependencies(ctx, cfg, func(db *mongo.Database) (preferenceports.Store, preferenceports.Reader, error) {
		store := preferencepersistence.NewMongoStore(db)
		if err := store.EnsureIndexes(ctx); err != nil {
			return nil, nil, err
		}
		return store, store, nil
	})
	if err != nil {
		return err
	}
	defer func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), runtimewiring.DependencyProbeTimeout)
		defer closeCancel()
		if closeErr := deps.Close(closeCtx); closeErr != nil {
			log.Printf("assistant environment seed dependency close failed: %v", closeErr)
		}
	}()

	learningProjector := learningprojection.NewMongoProjector(
		deps.MongoClient.Database(cfg.MongoDB.Database),
	)
	if err := learningProjector.EnsureIndexes(ctx); err != nil {
		return runtimewiring.NewDependencyError(
			"mongodb.rm_assistant_learning_projection",
			"indexes",
			err,
		)
	}
	service := application.NewAssistantService(
		deps.ConsentStore,
		router.Scene("general"),
		application.WithLearningProjectionReader(learningProjector),
		application.WithSkillSubscriptionStore(deps.SubscriptionStore),
	)
	result, err := environmentseed.Apply(ctx, service, plan)
	if err != nil {
		return err
	}
	payload, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal assistant seed report: %w", err)
	}
	if options.ReportPath != "" {
		if err := writeReport(options.ReportPath, payload); err != nil {
			return err
		}
	}
	fmt.Println(string(payload))
	return nil
}

func writeReport(path string, payload []byte) error {
	path = filepath.Clean(path)
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return fmt.Errorf("create assistant seed report directory: %w", err)
	}
	if err := os.WriteFile(path, append(payload, '\n'), 0o644); err != nil {
		return fmt.Errorf("write assistant seed report: %w", err)
	}
	return nil
}

func splitCSV(raw string) []string {
	out := []string{}
	seen := map[string]struct{}{}
	for _, item := range strings.Split(raw, ",") {
		item = strings.TrimSpace(item)
		if item == "" {
			continue
		}
		if _, ok := seen[item]; ok {
			continue
		}
		seen[item] = struct{}{}
		out = append(out, item)
	}
	return out
}

func seedTimeoutSeconds(raw string) int {
	if strings.TrimSpace(raw) == "" {
		return 90
	}
	value, err := strconv.Atoi(strings.TrimSpace(raw))
	if err != nil {
		return 0
	}
	return value
}
