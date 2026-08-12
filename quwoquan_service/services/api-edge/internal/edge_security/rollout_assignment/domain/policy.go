package domain

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/binary"
	"errors"
	"fmt"
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

type InternalCanary struct {
	AccountIDs     []string `yaml:"accountIds" json:"accountIds"`
	DeviceActorIDs []string `yaml:"deviceActorIds" json:"deviceActorIds"`
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
	Stages                         map[string]Stage `yaml:"stages" json:"stages"`
}

func (policy Policy) Validate() error {
	if !policy.Enabled {
		return nil
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
