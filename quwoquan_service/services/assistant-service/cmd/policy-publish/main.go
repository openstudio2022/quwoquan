// Command policy-publish stages and activates the immutable Assistant policy
// artifact explicitly referenced by a non-alpha runtime configuration.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	rtmongo "quwoquan_service/internal/platform/mongodb"
	"quwoquan_service/runtime/servicekit"
	releaseapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/application"
	releasepersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/infrastructure/persistence"
	releaseresource "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/infrastructure/resource"
	rolloutapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/application"
	rolloutpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/infrastructure/persistence"
	rolloutresource "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/infrastructure/resource"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/runtimeconfig"
)

const assistantServiceName = "assistant-service"

type options struct {
	Environment        string
	ConfigRoot         string
	ConfigVersion      string
	PolicyResourceRoot string
	Timeout            time.Duration
}

type report struct {
	PolicyID           string   `json:"policyId"`
	ReleaseDigest      string   `json:"releaseDigest"`
	RolloutRevision    int      `json:"rolloutRevision"`
	Cohorts            []string `json:"cohorts"`
	StageReplayed      bool     `json:"stageReplayed"`
	ActivationReplayed bool     `json:"activationReplayed"`
	PublicationCommand string   `json:"publicationCommand"`
}

func main() {
	opts, err := parseOptions(os.Args[1:], os.Getenv)
	if err != nil {
		log.Printf("assistant policy publisher options invalid: %v", err)
		os.Exit(2)
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if err := run(ctx, opts, os.Stdout); err != nil {
		log.Printf("assistant policy publisher failed: %v", err)
		os.Exit(1)
	}
}

func parseOptions(
	args []string,
	getenv func(string) string,
) (options, error) {
	flags := flag.NewFlagSet("assistant-policy-publish", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	environment := flags.String("env", strings.TrimSpace(getenv("APP_ENV")), "target environment")
	configRoot := flags.String("config-root", strings.TrimSpace(getenv("CONFIG_ROOT")), "runtime config root")
	configVersion := flags.String("config-version", strings.TrimSpace(getenv("CONFIG_VERSION")), "runtime config version")
	resourceRoot := flags.String("resource-root", strings.TrimSpace(getenv("ASSISTANT_POLICY_RESOURCE_ROOT")), "immutable policy resource root")
	timeoutSeconds := flags.Int("timeout-seconds", 60, "publication timeout")
	if err := flags.Parse(args); err != nil {
		return options{}, err
	}
	if flags.NArg() != 0 {
		return options{}, fmt.Errorf("unexpected positional arguments: %s", strings.Join(flags.Args(), " "))
	}
	switch strings.TrimSpace(*environment) {
	case "beta", "gamma", "prod":
	default:
		return options{}, fmt.Errorf("--env must be beta, gamma, or prod; alpha uses the contract mock")
	}
	if strings.TrimSpace(*configRoot) == "" ||
		strings.TrimSpace(*resourceRoot) == "" ||
		*timeoutSeconds <= 0 {
		return options{}, fmt.Errorf("config root, policy resource root, and positive timeout are required")
	}
	return options{
		Environment:        strings.TrimSpace(*environment),
		ConfigRoot:         strings.TrimSpace(*configRoot),
		ConfigVersion:      strings.TrimSpace(*configVersion),
		PolicyResourceRoot: strings.TrimSpace(*resourceRoot),
		Timeout:            time.Duration(*timeoutSeconds) * time.Second,
	}, nil
}

func run(parent context.Context, opts options, output io.Writer) error {
	ctx, cancel := context.WithTimeout(parent, opts.Timeout)
	defer cancel()
	cfg, err := loadAssistantRuntimeConfig(opts)
	if err != nil {
		return err
	}
	releaseRef := strings.TrimSpace(cfg.PolicyPublication.ReleaseArtifactRef)
	rolloutRef := strings.TrimSpace(cfg.PolicyPublication.RolloutArtifactRef)
	if releaseRef == "" || rolloutRef == "" {
		return fmt.Errorf("policy publication artifact references are required in runtime config")
	}
	releaseArtifact, err := releaseresource.LoadReleaseArtifact(
		opts.PolicyResourceRoot,
		releaseRef,
	)
	if err != nil {
		return fmt.Errorf("load policy release artifact: %w", err)
	}
	rolloutArtifact, err := loadRolloutArtifact(
		opts.PolicyResourceRoot,
		rolloutRef,
	)
	if err != nil {
		return fmt.Errorf("load policy rollout artifact: %w", err)
	}
	if rolloutArtifact.PolicyID != releaseArtifact.Release.PolicyID {
		return fmt.Errorf("rollout policy identity does not match release artifact")
	}
	for _, assignment := range rolloutArtifact.Assignments {
		if assignment.ReleaseDigest != releaseArtifact.Release.ReleaseDigest {
			return fmt.Errorf(
				"rollout assignment %q references undeclared release %q",
				assignment.Cohort,
				assignment.ReleaseDigest,
			)
		}
	}

	client, err := rtmongo.Connect(ctx, rtmongo.ConnectConfig{
		URI:      strings.TrimSpace(cfg.MongoDB.URI),
		Database: strings.TrimSpace(cfg.MongoDB.Database),
	})
	if err != nil {
		return fmt.Errorf("connect policy publication mongodb: %w", err)
	}
	defer func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer closeCancel()
		if closeErr := client.Disconnect(closeCtx); closeErr != nil {
			log.Printf("assistant policy publisher mongodb close failed: %v", closeErr)
		}
	}()
	database := client.Database(strings.TrimSpace(cfg.MongoDB.Database))
	releaseStore := releasepersistence.NewMongoStore(database)
	if err := releaseStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("ensure policy release indexes: %w", err)
	}
	rolloutStore := rolloutpersistence.NewMongoStore(database)
	if err := rolloutStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("ensure policy rollout indexes: %w", err)
	}
	releases := releaseapplication.NewService(releaseStore, nil)
	staged, err := releases.Stage(
		ctx,
		releaseArtifact.CommandID,
		releaseArtifact.Release,
	)
	if err != nil {
		return fmt.Errorf("stage policy release: %w", err)
	}
	rollouts := rolloutapplication.NewService(rolloutStore, releases, nil)
	activated, err := rollouts.Activate(
		ctx,
		rolloutArtifact.CommandID,
		rolloutapplication.ActivateInput{
			PolicyID:          rolloutArtifact.PolicyID,
			ExpectedRevision:  rolloutArtifact.ExpectedRevision,
			BucketDefinitions: rolloutArtifact.BucketDefinitions,
			Assignments:       rolloutArtifact.Assignments,
			ActivatedBy:       rolloutArtifact.ActivatedBy,
		},
	)
	if err != nil {
		return fmt.Errorf("activate policy rollout: %w", err)
	}
	cohorts := make([]string, 0, len(activated.Rollout.Assignments))
	for _, assignment := range activated.Rollout.Assignments {
		cohorts = append(cohorts, assignment.Cohort)
	}
	result := report{
		PolicyID:           staged.Release.PolicyID,
		ReleaseDigest:      staged.Release.ReleaseDigest,
		RolloutRevision:    activated.Rollout.Revision,
		Cohorts:            cohorts,
		StageReplayed:      staged.Replayed,
		ActivationReplayed: activated.Replayed,
		PublicationCommand: rolloutArtifact.CommandID,
	}
	encoded, err := json.Marshal(result)
	if err != nil {
		return fmt.Errorf("encode policy publication report: %w", err)
	}
	_, err = fmt.Fprintln(output, string(encoded))
	return err
}

func loadRolloutArtifact(
	resourceRoot string,
	reference string,
) (rolloutresource.RolloutArtifact, error) {
	path, err := releaseresource.ResolveArtifactPath(resourceRoot, reference)
	if err != nil {
		return rolloutresource.RolloutArtifact{}, fmt.Errorf(
			"%w: %v",
			rolloutresource.ErrInvalidArtifact,
			err,
		)
	}
	file, err := os.Open(path)
	if err != nil {
		return rolloutresource.RolloutArtifact{}, fmt.Errorf(
			"%w: open: %v",
			rolloutresource.ErrInvalidArtifact,
			err,
		)
	}
	defer file.Close()
	return rolloutresource.DecodeRolloutArtifact(file)
}

// loadAssistantRuntimeConfig 与服务进程读同一份渲染快照、同一套 env 覆盖
// 规则（servicekit），避免发布工具形成第二套配置解释。
func loadAssistantRuntimeConfig(opts options) (runtimeconfig.Config, error) {
	identity := servicekit.Identity{
		ServiceName:   assistantServiceName,
		AppEnv:        opts.Environment,
		ConfigRoot:    opts.ConfigRoot,
		ConfigVersion: opts.ConfigVersion,
	}
	cfg := runtimeconfig.Config{}
	if err := servicekit.LoadYAMLConfig(identity, &cfg); err != nil {
		return runtimeconfig.Config{}, fmt.Errorf("load assistant runtime config: %w", err)
	}
	if err := servicekit.ApplyEnvOverrides(
		servicekit.DefaultEnvPrefix(assistantServiceName), &cfg,
	); err != nil {
		return runtimeconfig.Config{}, fmt.Errorf("apply assistant runtime overrides: %w", err)
	}
	return cfg, nil
}
