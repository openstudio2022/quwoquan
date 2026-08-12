package application

import (
	"errors"
	"strconv"
	"strings"
)

type MinimumBuildPolicy struct {
	SourceDigest string
	Mode         string
	Platforms    map[string]uint64
}

func (policy MinimumBuildPolicy) Validate() error {
	if strings.TrimSpace(policy.SourceDigest) == "" {
		return errors.New("minimum build source digest is required")
	}
	if policy.Mode != "observe" && policy.Mode != "enforce" {
		return errors.New("minimum build mode must be observe or enforce")
	}
	for _, platform := range []string{"android", "ios", "web"} {
		if policy.Platforms[platform] == 0 {
			return errors.New("minimum build is required for android, ios, and web")
		}
	}
	return nil
}

type MinimumBuildDecision struct {
	Allowed    bool
	WouldBlock bool
	Reason     string
}

func (policy MinimumBuildPolicy) Decide(platform, rawBuild string) MinimumBuildDecision {
	platform = strings.TrimSpace(strings.ToLower(platform))
	minimum, knownPlatform := policy.Platforms[platform]
	build, err := strconv.ParseUint(strings.TrimSpace(rawBuild), 10, 64)
	wouldBlock := !knownPlatform || err != nil || build < minimum
	if !wouldBlock {
		return MinimumBuildDecision{Allowed: true, Reason: "supported"}
	}
	reason := "below_minimum"
	if !knownPlatform {
		reason = "unknown_platform"
	} else if err != nil {
		reason = "missing_or_invalid_build"
	}
	return MinimumBuildDecision{
		Allowed: policy.Mode == "observe", WouldBlock: true, Reason: reason,
	}
}
