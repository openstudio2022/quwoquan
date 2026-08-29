// Command skill-package-publish stages and activates one explicitly referenced
// signed official Skill package in a target environment.
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
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/runtimeconfig"
	packageapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application"
	packagemodel "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
	packageartifact "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/infrastructure/artifact"
	packagepersistence "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/infrastructure/persistence"
)

type options struct {
	Environment    string
	ConfigRoot     string
	ConfigVersion  string
	AssetRoot      string
	PublicationRef string
	Timeout        time.Duration
}

type report struct {
	Environment           string `json:"environment"`
	PackageID             string `json:"packageId"`
	ReleaseDigest         string `json:"releaseDigest"`
	ActivationRevision    int    `json:"activationRevision"`
	PreviousReleaseDigest string `json:"previousReleaseDigest,omitempty"`
	StageReplayed         bool   `json:"stageReplayed"`
	ActivationReplayed    bool   `json:"activationReplayed"`
	PublicationCommand    string `json:"publicationCommand"`
}

func main() {
	options, err := parseOptions(os.Args[1:], os.Getenv)
	if err != nil {
		log.Printf("assistant Skill package publisher options invalid: %v", err)
		os.Exit(2)
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if err := run(ctx, options, os.Stdout); err != nil {
		log.Printf("assistant Skill package publisher failed: %v", err)
		os.Exit(1)
	}
}

func parseOptions(
	args []string,
	getenv func(string) string,
) (options, error) {
	flags := flag.NewFlagSet("assistant-skill-package-publish", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	environment := flags.String("env", strings.TrimSpace(getenv("APP_ENV")), "target environment")
	configRoot := flags.String("config-root", strings.TrimSpace(getenv("CONFIG_ROOT")), "runtime config root")
	configVersion := flags.String("config-version", strings.TrimSpace(getenv("CONFIG_VERSION")), "runtime config version")
	assetRoot := flags.String("asset-root", strings.TrimSpace(getenv("ASSISTANT_SKILL_PACKAGE_ROOT")), "official package root")
	publicationRef := flags.String("publication-ref", "", "immutable publication artifact reference")
	timeoutSeconds := flags.Int("timeout-seconds", 60, "publication timeout")
	if err := flags.Parse(args); err != nil {
		return options{}, err
	}
	if flags.NArg() != 0 {
		return options{}, fmt.Errorf("unexpected positional arguments")
	}
	switch strings.TrimSpace(*environment) {
	case "alpha", "beta", "gamma", "prod":
	default:
		return options{}, fmt.Errorf("--env must be alpha, beta, gamma, or prod")
	}
	parsed := options{
		Environment:    strings.TrimSpace(*environment),
		ConfigRoot:     strings.TrimSpace(*configRoot),
		ConfigVersion:  strings.TrimSpace(*configVersion),
		AssetRoot:      strings.TrimSpace(*assetRoot),
		PublicationRef: strings.TrimSpace(*publicationRef),
		Timeout:        time.Duration(*timeoutSeconds) * time.Second,
	}
	if parsed.ConfigRoot == "" || parsed.AssetRoot == "" ||
		parsed.PublicationRef == "" || parsed.Timeout <= 0 {
		return options{}, fmt.Errorf("config root, asset root, publication ref, and positive timeout are required")
	}
	return parsed, nil
}

func run(parent context.Context, options options, output io.Writer) error {
	ctx, cancel := context.WithTimeout(parent, options.Timeout)
	defer cancel()
	cfg, err := loadAssistantRuntimeConfig(options)
	if err != nil {
		return err
	}
	publication, err := packageartifact.LoadPublicationArtifact(
		options.AssetRoot,
		options.PublicationRef,
	)
	if err != nil {
		return fmt.Errorf("load Skill package publication: %w", err)
	}
	trustedKeys, err := packageapplication.DecodeTrustedPublicKeys(
		cfg.SkillPackage.TrustedPublicKeysJSON,
	)
	if err != nil {
		return fmt.Errorf("decode trusted Skill package keys: %w", err)
	}
	assetReader, err := packageartifact.NewResourceReader(options.AssetRoot)
	if err != nil {
		return err
	}
	client, err := rtmongo.Connect(ctx, rtmongo.ConnectConfig{
		URI:      strings.TrimSpace(cfg.MongoDB.URI),
		Database: strings.TrimSpace(cfg.MongoDB.Database),
	})
	if err != nil {
		return fmt.Errorf("connect Skill package publication mongodb: %w", err)
	}
	defer func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer closeCancel()
		if closeErr := client.Disconnect(closeCtx); closeErr != nil {
			log.Printf("assistant Skill package publisher mongodb close failed: %v", closeErr)
		}
	}()
	store := packagepersistence.NewMongoStore(
		client.Database(strings.TrimSpace(cfg.MongoDB.Database)),
	)
	if err := store.EnsureIndexes(ctx); err != nil {
		return err
	}
	service := packageapplication.NewService(
		store,
		store,
		assetReader,
		packageapplication.NewEd25519Verifier(trustedKeys),
		packageapplication.RuntimeIdentity{
			APIVersion: packagemodel.RuntimeAPIVersion,
			Version:    packagemodel.RuntimeVersion,
		},
		time.Now,
	)
	staged, err := service.Stage(
		ctx,
		publication.CommandID+":stage",
		publication.Release,
	)
	if err != nil {
		return fmt.Errorf("stage Skill package release: %w", err)
	}
	activated, err := service.Activate(
		ctx,
		publication.CommandID+":activate",
		packageapplication.ActivateInput{
			PackageID:         staged.Release.PackageID,
			ReleaseDigest:     staged.Release.ReleaseDigest,
			ExpectedRevision:  publication.ExpectedRevision,
			ActivatedBy:       publication.ActivatedBy,
			EvaluationReceipt: publication.EvaluationReceipt,
		},
	)
	if err != nil {
		return fmt.Errorf("activate Skill package release: %w", err)
	}
	return json.NewEncoder(output).Encode(report{
		Environment:           options.Environment,
		PackageID:             activated.Activation.PackageID,
		ReleaseDigest:         activated.Activation.ActiveReleaseDigest,
		ActivationRevision:    activated.Activation.Revision,
		PreviousReleaseDigest: activated.Activation.PreviousReleaseDigest,
		StageReplayed:         staged.Replayed,
		ActivationReplayed:    activated.Replayed,
		PublicationCommand:    publication.CommandID,
	})
}

// loadAssistantRuntimeConfig 与服务进程读同一份渲染快照、同一套 env 覆盖
// 规则（servicekit），避免发布工具形成第二套配置解释。
func loadAssistantRuntimeConfig(opts options) (runtimeconfig.Config, error) {
	identity := servicekit.Identity{
		ServiceName:   "assistant-service",
		AppEnv:        opts.Environment,
		ConfigRoot:    opts.ConfigRoot,
		ConfigVersion: opts.ConfigVersion,
	}
	cfg := runtimeconfig.Config{}
	if err := servicekit.LoadYAMLConfig(identity, &cfg); err != nil {
		return runtimeconfig.Config{}, fmt.Errorf("load assistant runtime config: %w", err)
	}
	if err := servicekit.ApplyEnvOverrides(
		servicekit.DefaultEnvPrefix("assistant-service"), &cfg,
	); err != nil {
		return runtimeconfig.Config{}, fmt.Errorf("apply assistant runtime overrides: %w", err)
	}
	return cfg, nil
}
