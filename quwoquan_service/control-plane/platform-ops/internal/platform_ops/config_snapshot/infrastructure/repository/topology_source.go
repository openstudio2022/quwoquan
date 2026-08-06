package repository

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"os"
	"path/filepath"
	"sort"
	"strings"

	configapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_snapshot/application/config_layer"

	"gopkg.in/yaml.v3"
)

type TopologySource struct {
	repositoryRoot string
	configRoot     string
}

func NewTopologySource(repositoryRoot string, configRoot string) (*TopologySource, error) {
	repositoryRoot = strings.TrimSpace(repositoryRoot)
	if repositoryRoot == "" {
		return nil, errors.New("config snapshot topology repository root is required")
	}
	return &TopologySource{
		repositoryRoot: repositoryRoot,
		configRoot:     strings.TrimSpace(configRoot),
	}, nil
}

func (source *TopologySource) ReadRuntimeTopology(
	ctx context.Context,
) (configapp.RuntimeTopology, error) {
	if err := ctx.Err(); err != nil {
		return configapp.RuntimeTopology{}, err
	}
	topology := configapp.RuntimeTopology{
		Environments: make(map[string]configapp.RuntimeTopologyEnvironment, 4),
		Targets:      make(map[string]configapp.RuntimeTopologyTarget),
	}
	servicesRoot := filepath.Join(source.repositoryRoot, "quwoquan_service", "services")
	services, err := os.ReadDir(servicesRoot)
	if err != nil {
		return topology, err
	}
	externalRoot := filepath.Join(source.repositoryRoot, "quwoquan_ops", "external")
	externals, err := os.ReadDir(externalRoot)
	if err != nil {
		return topology, err
	}
	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		entry := configapp.RuntimeTopologyEnvironment{}
		for _, service := range services {
			if !service.IsDir() {
				continue
			}
			deployDir := filepath.Join(servicesRoot, service.Name(), "environments", environment, "deploy")
			if _, statErr := os.Stat(filepath.Join(deployDir, "kustomization.yaml")); statErr != nil {
				continue
			}
			entry.Workloads = append(entry.Workloads, configapp.RuntimeTopologyWorkload{
				ID: service.Name(), Plane: workloadPlane(service.Name()),
				DeploymentRef: relativePath(source.repositoryRoot, deployDir),
			})
		}
		for _, external := range externals {
			if !external.IsDir() {
				continue
			}
			deployDir := filepath.Join(externalRoot, external.Name(), "environments", environment)
			if _, statErr := os.Stat(filepath.Join(deployDir, "kustomization.yaml")); statErr != nil {
				continue
			}
			entry.Workloads = append(entry.Workloads, configapp.RuntimeTopologyWorkload{
				ID: external.Name(), Plane: workloadPlane(external.Name()),
				DeploymentRef: relativePath(source.repositoryRoot, deployDir),
			})
		}
		platformDeploy := filepath.Join(source.repositoryRoot, "quwoquan_ops", "platform", "deploy", "base")
		if _, statErr := os.Stat(filepath.Join(platformDeploy, "kustomization.yaml")); statErr == nil {
			entry.Workloads = append(entry.Workloads, configapp.RuntimeTopologyWorkload{
				ID: "platform-ops-service", Plane: "service",
				DeploymentRef: relativePath(source.repositoryRoot, platformDeploy),
			})
		}
		sort.Slice(entry.Workloads, func(i, j int) bool { return entry.Workloads[i].ID < entry.Workloads[j].ID })
		topology.Environments[environment] = entry

		var runtime struct {
			Targets map[string]struct {
				Environment string `yaml:"env"`
			} `yaml:"targets"`
		}
		if err := readYAML(filepath.Join(source.repositoryRoot, "quwoquan_ops", "environments", environment, "runtime.yaml"), &runtime); err != nil {
			return topology, err
		}
		for targetID, target := range runtime.Targets {
			topology.Targets[targetID] = configapp.RuntimeTopologyTarget{Environment: target.Environment}
		}
	}
	return topology, nil
}

func (source *TopologySource) ReadGrayRoutingPolicy(
	ctx context.Context,
) (configapp.GrayRoutingPolicySnapshot, error) {
	if err := ctx.Err(); err != nil {
		return configapp.GrayRoutingPolicySnapshot{}, err
	}
	candidates := make([]string, 0, 2)
	if source.configRoot != "" {
		candidates = append(candidates, filepath.Join(source.configRoot, "gray-routing", "policy.yaml"))
	}
	candidates = append(candidates, filepath.Join(
		source.repositoryRoot, "quwoquan_ops", "environments", "prod", "rollout", "routing_policy.yaml",
	))
	for _, path := range candidates {
		raw, err := os.ReadFile(path)
		if err != nil {
			continue
		}
		var document struct {
			Policy configapp.GrayRoutingPolicy `yaml:"policy"`
		}
		if err := yaml.Unmarshal(raw, &document); err != nil {
			return configapp.GrayRoutingPolicySnapshot{}, err
		}
		for _, stage := range []string{"gray-initial", "carry-on", "full"} {
			if _, found := document.Policy.StageDimensions[stage]; !found {
				return configapp.GrayRoutingPolicySnapshot{}, errors.New("gray routing policy missing canonical rollout stage")
			}
		}
		return configapp.GrayRoutingPolicySnapshot{
			Policy: document.Policy,
			Source: sourceEvidence(source.repositoryRoot, path, raw),
		}, nil
	}
	return configapp.GrayRoutingPolicySnapshot{}, os.ErrNotExist
}

func (source *TopologySource) ReadProdPlaneAccessIsolation(
	ctx context.Context,
) (configapp.ProdPlaneAccessIsolationSnapshot, error) {
	if err := ctx.Err(); err != nil {
		return configapp.ProdPlaneAccessIsolationSnapshot{}, err
	}
	path := filepath.Join(source.repositoryRoot, "quwoquan_ops", "environments", "prod", "access-isolation.yaml")
	raw, err := os.ReadFile(path)
	if err != nil {
		return configapp.ProdPlaneAccessIsolationSnapshot{}, err
	}
	var document struct {
		Schema string `yaml:"schema"`
		Target string `yaml:"target"`
		Relay  struct {
			Name string `yaml:"name"`
		} `yaml:"relayAccount"`
		Planes []struct {
			Plane            string   `yaml:"plane"`
			Account          string   `yaml:"account"`
			SSHKeySecret     string   `yaml:"sshKeySecret"`
			Access           string   `yaml:"access"`
			RuntimeContainer string   `yaml:"runtimeContainer"`
			RolloutStages    []string `yaml:"appliesToStages"`
		} `yaml:"planes"`
	}
	if err := yaml.Unmarshal(raw, &document); err != nil {
		return configapp.ProdPlaneAccessIsolationSnapshot{}, err
	}
	if document.Schema != "prod-plane-access-isolation" || strings.TrimSpace(document.Target) == "" || strings.TrimSpace(document.Relay.Name) == "" {
		return configapp.ProdPlaneAccessIsolationSnapshot{}, errors.New("prod plane access isolation identity is incomplete")
	}
	required := map[string]bool{"edge": false, "media": false, "service": false, "data": false}
	accounts := make([]configapp.PlaneAccessEvidence, 0, len(document.Planes))
	for _, plane := range document.Planes {
		if _, known := required[plane.Plane]; !known || required[plane.Plane] ||
			strings.TrimSpace(plane.Account) == "" || strings.TrimSpace(plane.SSHKeySecret) == "" ||
			strings.TrimSpace(plane.Access) == "" {
			return configapp.ProdPlaneAccessIsolationSnapshot{}, errors.New("prod plane access isolation plane binding is incomplete")
		}
		required[plane.Plane] = true
		accounts = append(accounts, configapp.PlaneAccessEvidence{
			Plane: plane.Plane, Account: plane.Account, Access: plane.Access,
			RuntimeContainer: plane.RuntimeContainer, RolloutStages: plane.RolloutStages,
		})
	}
	planes := make([]string, 0, len(required))
	for _, plane := range []string{"edge", "media", "service", "data"} {
		if !required[plane] {
			return configapp.ProdPlaneAccessIsolationSnapshot{}, errors.New("prod plane access isolation must bind all four planes")
		}
		planes = append(planes, plane)
	}
	sort.Slice(accounts, func(i, j int) bool { return accounts[i].Plane < accounts[j].Plane })
	return configapp.ProdPlaneAccessIsolationSnapshot{
		Environment: "prod", Plane: planes, DirectAccessAllowed: false,
		Evidence: configapp.ProdPlaneIsolationEvidence{
			Source: sourceEvidence(source.repositoryRoot, path, raw), Target: document.Target,
			RelayAccount: document.Relay.Name, Accounts: accounts,
		},
	}, nil
}

func sourceEvidence(repositoryRoot string, path string, raw []byte) configapp.SourceEvidence {
	digest := sha256.Sum256(raw)
	return configapp.SourceEvidence{
		Path: relativePath(repositoryRoot, path), SHA256: "sha256:" + hex.EncodeToString(digest[:]),
	}
}

func readYAML(path string, target any) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return yaml.Unmarshal(raw, target)
}

func workloadPlane(workloadID string) string {
	if workloadID == "realtime-gateway" {
		return "edge"
	}
	if workloadID == "rtc-service" || workloadID == "coturn" || workloadID == "livekit" {
		return "media"
	}
	return "service"
}

func relativePath(repositoryRoot string, target string) string {
	relative, err := filepath.Rel(repositoryRoot, target)
	if err != nil {
		return filepath.ToSlash(target)
	}
	return filepath.ToSlash(relative)
}
