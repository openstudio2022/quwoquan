package config_layer

import (
	"context"
	"errors"
	"sort"
)

type RuntimeTopology struct {
	Environments map[string]RuntimeTopologyEnvironment
	Targets      map[string]RuntimeTopologyTarget
}

type RuntimeTopologyEnvironment struct {
	Workloads []RuntimeTopologyWorkload
}

type RuntimeTopologyWorkload struct {
	ID            string
	Plane         string
	DeploymentRef string
}

type RuntimeTopologyTarget struct {
	Environment string
}

type SourceEvidence struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
}

type RolloutSelector struct {
	Mode   string   `yaml:"mode" json:"mode"`
	Values []string `yaml:"values" json:"values"`
}

type RolloutStagePolicy struct {
	BasisPoints int             `yaml:"basisPoints" json:"basisPoints"`
	AppVersions RolloutSelector `yaml:"appVersions" json:"appVersions"`
	Platforms   RolloutSelector `yaml:"platforms" json:"platforms"`
	Regions     RolloutSelector `yaml:"regions" json:"regions"`
	Carriers    RolloutSelector `yaml:"carriers" json:"carriers"`
}

type RolloutInternalCanary struct {
	AccountIDs     []string `yaml:"accountIds" json:"accountIds"`
	DeviceActorIDs []string `yaml:"deviceActorIds" json:"deviceActorIds"`
}

type GrayRoutingPolicy struct {
	Enabled                        bool                          `yaml:"enabled" json:"enabled"`
	CampaignID                     string                        `yaml:"campaignId" json:"campaignId"`
	CandidateDigest                string                        `yaml:"candidateDigest" json:"candidateDigest"`
	AllocationKeyID                string                        `yaml:"allocationKeyId" json:"allocationKeyId"`
	SubjectKind                    string                        `yaml:"subjectKind" json:"subjectKind"`
	Stage                          string                        `yaml:"stage" json:"stage"`
	Status                         string                        `yaml:"status" json:"status"`
	CandidateUpstream              string                        `yaml:"candidateUpstream" json:"candidateUpstream"`
	AssignmentTTLDaysAfterCampaign int                           `yaml:"assignmentTtlDaysAfterCampaign" json:"assignmentTtlDaysAfterCampaign"`
	InternalCanary                 RolloutInternalCanary         `yaml:"internalCanary" json:"internalCanary"`
	Stages                         map[string]RolloutStagePolicy `yaml:"stages" json:"stages"`
}

type GrayRoutingPolicySnapshot struct {
	Policy GrayRoutingPolicy `json:"policy"`
	Source SourceEvidence    `json:"source"`
}

type PlaneAccessEvidence struct {
	Plane            string   `json:"plane"`
	Account          string   `json:"account"`
	Access           string   `json:"access"`
	RuntimeContainer string   `json:"runtimeContainer"`
	RolloutStages    []string `json:"rolloutStages"`
}

type ProdPlaneIsolationEvidence struct {
	Source       SourceEvidence        `json:"source"`
	Target       string                `json:"target"`
	RelayAccount string                `json:"relayAccount"`
	Accounts     []PlaneAccessEvidence `json:"accounts"`
}

type ProdPlaneAccessIsolationSnapshot struct {
	Environment         string                     `json:"environment"`
	Plane               []string                   `json:"plane"`
	DirectAccessAllowed bool                       `json:"directAccessAllowed"`
	Evidence            ProdPlaneIsolationEvidence `json:"evidence"`
}

type TopologySnapshotSource interface {
	ReadRuntimeTopology(context.Context) (RuntimeTopology, error)
	ReadGrayRoutingPolicy(context.Context) (GrayRoutingPolicySnapshot, error)
	ReadProdPlaneAccessIsolation(context.Context) (ProdPlaneAccessIsolationSnapshot, error)
}

type TopologyFacade struct {
	source TopologySnapshotSource
}

func NewTopologyFacade(source TopologySnapshotSource) (*TopologyFacade, error) {
	if source == nil {
		return nil, errors.New("config snapshot topology facade requires source")
	}
	return &TopologyFacade{source: source}, nil
}

func (facade *TopologyFacade) ListServiceCatalogEntries(
	ctx context.Context,
) ([]map[string]any, error) {
	topology, err := facade.source.ReadRuntimeTopology(ctx)
	if err != nil {
		return nil, err
	}
	type catalogEntry struct {
		planes         map[string]struct{}
		deploymentRefs map[string]struct{}
	}
	byWorkload := map[string]*catalogEntry{}
	for _, environment := range topology.Environments {
		for _, workload := range environment.Workloads {
			entry := byWorkload[workload.ID]
			if entry == nil {
				entry = &catalogEntry{planes: map[string]struct{}{}, deploymentRefs: map[string]struct{}{}}
				byWorkload[workload.ID] = entry
			}
			entry.planes[workload.Plane] = struct{}{}
			entry.deploymentRefs[workload.DeploymentRef] = struct{}{}
		}
	}
	items := make([]map[string]any, 0, len(byWorkload))
	for workloadID, entry := range byWorkload {
		items = append(items, map[string]any{
			"id": workloadID, "service": workloadID,
			"plane": joinSorted(entry.planes), "owner": "environment-topology",
			"health": "neutral", "summary": joinSorted(entry.deploymentRefs),
		})
	}
	sort.Slice(items, func(i, j int) bool { return items[i]["service"].(string) < items[j]["service"].(string) })
	return items, nil
}

func (facade *TopologyFacade) ListPlaneBindings(
	ctx context.Context,
) ([]map[string]any, error) {
	return facade.listBindings(ctx)
}

func (facade *TopologyFacade) ListEnvironmentTopologies(
	ctx context.Context,
) ([]map[string]any, error) {
	return facade.listBindings(ctx)
}

func (facade *TopologyFacade) listBindings(ctx context.Context) ([]map[string]any, error) {
	topology, err := facade.source.ReadRuntimeTopology(ctx)
	if err != nil {
		return nil, err
	}
	items := make([]map[string]any, 0)
	for environment, value := range topology.Environments {
		for _, workload := range value.Workloads {
			items = append(items, map[string]any{
				"id": environment + ":" + workload.ID, "env": environment,
				"workload": workload.ID, "plane": workload.Plane,
				"deploymentRef": workload.DeploymentRef,
			})
		}
	}
	sort.Slice(items, func(i, j int) bool { return items[i]["id"].(string) < items[j]["id"].(string) })
	return items, nil
}

func (facade *TopologyFacade) ListRuntimeClusters(
	ctx context.Context,
) ([]map[string]any, error) {
	topology, err := facade.source.ReadRuntimeTopology(ctx)
	if err != nil {
		return nil, err
	}
	items := make([]map[string]any, 0, len(topology.Environments))
	for environment, value := range topology.Environments {
		services := make([]string, 0, len(value.Workloads))
		for _, workload := range value.Workloads {
			services = append(services, workload.ID)
		}
		sort.Strings(services)
		items = append(items, map[string]any{
			"id":          environment + ":" + deploymentTarget(topology, environment),
			"environment": environment, "cluster": deploymentTarget(topology, environment),
			"plane": "service-plane", "services": services, "status": "declared",
		})
	}
	sort.Slice(items, func(i, j int) bool { return items[i]["id"].(string) < items[j]["id"].(string) })
	return items, nil
}

func (facade *TopologyFacade) GetGrayRoutingPolicy(
	ctx context.Context,
) (GrayRoutingPolicySnapshot, error) {
	return facade.source.ReadGrayRoutingPolicy(ctx)
}

func (facade *TopologyFacade) GetProdPlaneAccessIsolation(
	ctx context.Context,
) (ProdPlaneAccessIsolationSnapshot, error) {
	return facade.source.ReadProdPlaneAccessIsolation(ctx)
}

func deploymentTarget(topology RuntimeTopology, environment string) string {
	preferred := environment + "-local"
	if environment == "prod" {
		preferred = "prod-hosted"
	}
	if target, found := topology.Targets[preferred]; found && target.Environment == environment {
		return preferred
	}
	for targetID, target := range topology.Targets {
		if target.Environment == environment {
			return targetID
		}
	}
	return environment
}

func joinSorted(values map[string]struct{}) string {
	items := make([]string, 0, len(values))
	for value := range values {
		items = append(items, value)
	}
	sort.Strings(items)
	result := ""
	for index, item := range items {
		if index > 0 {
			result += " · "
		}
		result += item
	}
	return result
}
