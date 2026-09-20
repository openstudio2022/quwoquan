package domain

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/binary"
	"errors"
	"fmt"
	"net/netip"
	"regexp"
	"strings"
)

type Target string

const (
	TargetStable           Target = "stable"
	TargetCandidate        Target = "candidate"
	SubjectKindDeviceActor        = "device_actor"
)

var stageOrder = []string{"canary", "5", "20", "50", "100"}

var (
	candidateDigestPattern   = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)
	versionPattern           = regexp.MustCompile(`^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$`)
	buildNumberPattern       = regexp.MustCompile(`^[1-9][0-9]*$`)
	networkAttributePattern  = regexp.MustCompile(`^[a-z0-9][a-z0-9._-]{0,31}$`)
	expectedStageBasisPoints = map[string]int{
		"canary": 0,
		"5":      500,
		"20":     2000,
		"50":     5000,
		"100":    10000,
	}
)

type Selector struct {
	Mode   string   `yaml:"mode" json:"mode"`
	Values []string `yaml:"values" json:"values"`
}

type Stage struct {
	BasisPoints int      `yaml:"basisPoints" json:"basisPoints"`
	AppVersions Selector `yaml:"appVersions" json:"appVersions"`
	Platforms   Selector `yaml:"platforms" json:"platforms"`
	Regions     Selector `yaml:"regions" json:"regions"`
	Carriers    Selector `yaml:"carriers" json:"carriers"`
}

type AppVersion struct {
	Platform       string `yaml:"platform" json:"platform"`
	DisplayVersion string `yaml:"displayVersion" json:"displayVersion"`
	BuildNumber    string `yaml:"buildNumber" json:"buildNumber"`
	ArtifactDigest string `yaml:"artifactDigest" json:"artifactDigest"`
}

type InternalCanary struct {
	AccountIDs     []string `yaml:"accountIds" json:"accountIds"`
	DeviceActorIDs []string `yaml:"deviceActorIds" json:"deviceActorIds"`
	TrustedIPCidrs []string `yaml:"trustedIpCidrs" json:"trustedIpCidrs"`
}

type RouteBinding struct {
	Target              Target `yaml:"target" json:"target"`
	DeploymentInstance  string `yaml:"deploymentInstance" json:"deploymentInstance"`
	CandidateID         string `yaml:"candidateId" json:"candidateId"`
	ArtifactDigest      string `yaml:"artifactDigest" json:"artifactDigest"`
	RuntimeConfigDigest string `yaml:"runtimeConfigDigest" json:"runtimeConfigDigest"`
	PublicExposure      bool   `yaml:"publicExposure" json:"publicExposure"`
}

// ValidationRing is an optional, fail-closed route restriction for an internal
// hosted validation ring. The ordinary percentage rollout remains compatible
// when this section is absent or disabled.
type ValidationRing struct {
	Enabled   bool         `yaml:"enabled" json:"enabled"`
	Route     RouteBinding `yaml:"route" json:"route"`
	RequireIP bool         `yaml:"requireIp" json:"requireIp"`
}

type Policy struct {
	Enabled                        bool             `yaml:"enabled" json:"enabled"`
	CampaignID                     string           `yaml:"campaignId" json:"campaignId"`
	CandidateDigest                string           `yaml:"candidateDigest" json:"candidateDigest"`
	AllocationKeyID                string           `yaml:"allocationKeyId" json:"allocationKeyId"`
	SubjectKind                    string           `yaml:"subjectKind" json:"subjectKind"`
	Stage                          string           `yaml:"stage" json:"stage"`
	Status                         string           `yaml:"status" json:"status"`
	CandidateUpstream              string           `yaml:"candidateUpstream" json:"candidateUpstream"`
	AssignmentTTLDaysAfterCampaign int              `yaml:"assignmentTtlDaysAfterCampaign" json:"assignmentTtlDaysAfterCampaign"`
	InternalCanary                 InternalCanary   `yaml:"internalCanary" json:"internalCanary"`
	AppVersions                    []AppVersion     `yaml:"appVersions" json:"appVersions"`
	ValidationRing                 ValidationRing   `yaml:"validationRing" json:"validationRing"`
	Stages                         map[string]Stage `yaml:"stages" json:"stages"`
}

func (policy Policy) Validate() error {
	if !policy.Enabled {
		return nil
	}
	if len(policy.AppVersions) > 0 {
		if err := validateAppVersions(policy.AppVersions); err != nil {
			return err
		}
	}
	if err := validateValidationRing(policy); err != nil {
		return err
	}
	if strings.TrimSpace(policy.CampaignID) == "" ||
		strings.TrimSpace(policy.CandidateDigest) == "" ||
		strings.TrimSpace(policy.AllocationKeyID) == "" {
		return errors.New("rollout campaign identity is required")
	}
	if !candidateDigestPattern.MatchString(policy.CandidateDigest) {
		return errors.New("rollout candidateDigest must be canonical sha256")
	}
	if policy.SubjectKind != SubjectKindDeviceActor {
		return errors.New("rollout subjectKind must be device_actor")
	}
	if policy.Status != "active" && policy.Status != "paused" &&
		policy.Status != "rolled_back" && policy.Status != "complete" {
		return fmt.Errorf("rollout status %q is invalid", policy.Status)
	}
	if policy.AssignmentTTLDaysAfterCampaign != 30 {
		return errors.New("rollout assignment retention must be 30 days")
	}
	if _, ok := policy.Stages[policy.Stage]; !ok {
		return fmt.Errorf("rollout stage %q is missing", policy.Stage)
	}
	previousBasisPoints := -1
	var previous audienceSets
	for index, name := range stageOrder {
		stage, ok := policy.Stages[name]
		if !ok {
			return fmt.Errorf("rollout stage %q is required", name)
		}
		if stage.BasisPoints != expectedStageBasisPoints[name] {
			return fmt.Errorf(
				"rollout stage %q basis points=%d must equal %d",
				name,
				stage.BasisPoints,
				expectedStageBasisPoints[name],
			)
		}
		if stage.BasisPoints < previousBasisPoints {
			return fmt.Errorf("rollout stage %q basis points are not monotonic", name)
		}
		if err := validateStage(name, stage); err != nil {
			return err
		}
		current := newAudienceSets(stage)
		if index != 0 && !previous.subsetOf(current) {
			return fmt.Errorf("rollout stage %q audience shrinks the previous stage", name)
		}
		previous = current
		previousBasisPoints = stage.BasisPoints
	}
	terminal := policy.Stages["100"]
	if terminal.BasisPoints != 10000 || terminal.AppVersions.Mode != "supported" ||
		terminal.Regions.Mode != "all" || terminal.Carriers.Mode != "all" ||
		!sameSet(terminal.Platforms.Values, []string{"android", "ios", "web"}) {
		return errors.New("rollout stage 100 must restore all supported platforms and network audiences")
	}
	return nil
}

func validateAppVersions(versions []AppVersion) error {
	if len(versions) == 0 {
		return errors.New("rollout appVersions must not be empty")
	}
	seen := make(map[string]struct{}, len(versions))
	for _, version := range versions {
		platform := strings.TrimSpace(version.Platform)
		displayVersion := strings.TrimSpace(version.DisplayVersion)
		buildNumber := strings.TrimSpace(version.BuildNumber)
		artifactDigest := strings.ToLower(strings.TrimSpace(version.ArtifactDigest))
		if platform != "ios" && platform != "android" && platform != "web" {
			return fmt.Errorf("rollout appVersion platform %q is invalid", platform)
		}
		if !versionPattern.MatchString(displayVersion) {
			return fmt.Errorf("rollout appVersion %q displayVersion is invalid", displayVersion)
		}
		if !buildNumberPattern.MatchString(buildNumber) {
			return fmt.Errorf("rollout appVersion %q buildNumber is invalid", displayVersion)
		}
		if !candidateDigestPattern.MatchString(artifactDigest) {
			return fmt.Errorf("rollout appVersion %q artifactDigest is invalid", displayVersion)
		}
		key := platform + "\x00" + displayVersion + "\x00" + buildNumber
		if _, exists := seen[key]; exists {
			return fmt.Errorf("rollout appVersion %q/%s is duplicated", displayVersion, buildNumber)
		}
		seen[key] = struct{}{}
	}
	return nil
}

func validateValidationRing(policy Policy) error {
	if !policy.ValidationRing.Enabled {
		return nil
	}
	ring := policy.ValidationRing
	if policy.Stage != "canary" {
		return errors.New("validation ring cannot share percentage rollout stages")
	}
	if ring.Route.CandidateID != policy.CandidateDigest {
		return errors.New("validation ring candidate digest differs from campaign")
	}
	if err := validateAppVersions(policy.AppVersions); err != nil {
		return err
	}
	for _, version := range policy.AppVersions {
		if version.ArtifactDigest != ring.Route.ArtifactDigest {
			return errors.New("validation ring app artifact differs from route binding")
		}
	}
	if ring.Route.Target != TargetCandidate {
		return errors.New("validation ring route target must be candidate")
	}
	if strings.TrimSpace(ring.Route.DeploymentInstance) != "prevalidate" {
		return errors.New("validation ring deployment instance must be prevalidate")
	}
	if !candidateDigestPattern.MatchString(strings.ToLower(strings.TrimSpace(ring.Route.CandidateID))) ||
		!candidateDigestPattern.MatchString(strings.ToLower(strings.TrimSpace(ring.Route.ArtifactDigest))) {
		return errors.New("validation ring candidate and artifact digests must be canonical sha256")
	}
	if !candidateDigestPattern.MatchString(strings.ToLower(strings.TrimSpace(ring.Route.RuntimeConfigDigest))) {
		return errors.New("validation ring runtimeConfigDigest must be canonical sha256")
	}
	if ring.Route.PublicExposure {
		return errors.New("validation ring must not be publicly exposed")
	}
	for _, raw := range policy.InternalCanary.TrustedIPCidrs {
		if _, err := netip.ParsePrefix(strings.TrimSpace(raw)); err != nil {
			return fmt.Errorf("validation ring trusted IP CIDR %q is invalid", raw)
		}
	}
	return nil
}

func validateStage(name string, stage Stage) error {
	if stage.Platforms.Mode != "include" || len(stage.Platforms.Values) == 0 {
		return fmt.Errorf("rollout stage %q platforms must use non-empty include mode", name)
	}
	for _, platform := range stage.Platforms.Values {
		if platform != "android" && platform != "ios" && platform != "web" {
			return fmt.Errorf("rollout stage %q platform %q is invalid", name, platform)
		}
	}
	if stage.AppVersions.Mode != "supported" && stage.AppVersions.Mode != "include" {
		return fmt.Errorf("rollout stage %q appVersions mode is invalid", name)
	}
	if stage.AppVersions.Mode == "supported" && len(stage.AppVersions.Values) != 0 {
		return fmt.Errorf("rollout stage %q supported appVersions must not list values", name)
	}
	for label, selector := range map[string]Selector{"regions": stage.Regions, "carriers": stage.Carriers} {
		if selector.Mode != "all" && selector.Mode != "include" {
			return fmt.Errorf("rollout stage %q %s mode is invalid", name, label)
		}
		if selector.Mode == "all" && len(selector.Values) != 0 {
			return fmt.Errorf("rollout stage %q %s all mode must not list values", name, label)
		}
		if selector.Mode == "include" && len(selector.Values) == 0 {
			return fmt.Errorf("rollout stage %q %s include mode must list values", name, label)
		}
		for _, value := range selector.Values {
			value = strings.TrimSpace(value)
			if !networkAttributePattern.MatchString(value) {
				return fmt.Errorf("rollout stage %q %s value %q is invalid", name, label, value)
			}
		}
	}
	return nil
}

// RequiresNetworkAttributeCatalog reports whether any stage targets a named
// region or carrier. The explicit unknown audience remains available without a
// catalog because it is the fail-closed result for every unrecognized address.
func (policy Policy) RequiresNetworkAttributeCatalog() bool {
	if !policy.Enabled {
		return false
	}
	for _, stage := range policy.Stages {
		for _, selector := range []Selector{stage.Regions, stage.Carriers} {
			if selector.Mode != "include" {
				continue
			}
			for _, value := range selector.Values {
				if strings.TrimSpace(value) != "unknown" {
					return true
				}
			}
		}
	}
	return false
}

func Bucket(key []byte, policy Policy, platform, deviceActorID string) (int, error) {
	if len(key) < 32 {
		return 0, errors.New("rollout allocation key must contain at least 32 bytes")
	}
	platform = strings.TrimSpace(platform)
	deviceActorID = strings.TrimSpace(deviceActorID)
	if platform == "" || deviceActorID == "" {
		return 0, errors.New("rollout platform and device actor are required")
	}
	material := policy.CampaignID + "\x00" + policy.CandidateDigest + "\x00" +
		platform + "\x00" + deviceActorID
	digest := hmac.New(sha256.New, key)
	_, _ = digest.Write([]byte(material))
	return int(binary.BigEndian.Uint64(digest.Sum(nil)[:8]) % 10000), nil
}

func SubjectDigest(key []byte, campaignID, deviceActorID string) (string, error) {
	if len(key) < 32 || strings.TrimSpace(campaignID) == "" || strings.TrimSpace(deviceActorID) == "" {
		return "", errors.New("rollout subject digest material is incomplete")
	}
	digest := hmac.New(sha256.New, key)
	_, _ = digest.Write([]byte(campaignID + "\x00" + deviceActorID))
	return fmt.Sprintf("%x", digest.Sum(nil)), nil
}

func (stage Stage) AudienceMatches(platform, appVersion, region, carrier string) bool {
	return stage.Platforms.matches(platform) && stage.AppVersions.matches(appVersion) &&
		stage.Regions.matches(normalizeNetworkAttribute(region)) &&
		stage.Carriers.matches(normalizeNetworkAttribute(carrier))
}

func (selector Selector) matches(value string) bool {
	if selector.Mode == "all" || selector.Mode == "supported" {
		return true
	}
	value = strings.TrimSpace(value)
	for _, candidate := range selector.Values {
		if value == strings.TrimSpace(candidate) {
			return true
		}
	}
	return false
}

func normalizeNetworkAttribute(value string) string {
	if value = strings.TrimSpace(value); value != "" {
		return value
	}
	return "unknown"
}

type audienceSets struct {
	platforms, appVersions, regions, carriers dimensionSet
}

func newAudienceSets(stage Stage) audienceSets {
	return audienceSets{
		platforms: dimensionSet{values: set(stage.Platforms.Values)},
		appVersions: dimensionSet{
			universal: stage.AppVersions.Mode == "supported",
			values:    set(stage.AppVersions.Values),
		},
		regions: dimensionSet{
			universal: stage.Regions.Mode == "all",
			values:    set(stage.Regions.Values),
		},
		carriers: dimensionSet{
			universal: stage.Carriers.Mode == "all",
			values:    set(stage.Carriers.Values),
		},
	}
}

func (left audienceSets) subsetOf(right audienceSets) bool {
	return left.platforms.subsetOf(right.platforms) && left.appVersions.subsetOf(right.appVersions) &&
		left.regions.subsetOf(right.regions) && left.carriers.subsetOf(right.carriers)
}

type dimensionSet struct {
	universal bool
	values    map[string]struct{}
}

func (left dimensionSet) subsetOf(right dimensionSet) bool {
	if right.universal {
		return true
	}
	if left.universal {
		return false
	}
	return subset(left.values, right.values)
}

func set(values []string) map[string]struct{} {
	result := make(map[string]struct{}, len(values))
	for _, value := range values {
		result[strings.TrimSpace(value)] = struct{}{}
	}
	return result
}

func subset(left, right map[string]struct{}) bool {
	for value := range left {
		if _, ok := right[value]; !ok {
			return false
		}
	}
	return true
}

func sameSet(left, right []string) bool {
	return subset(set(left), set(right)) && subset(set(right), set(left))
}
