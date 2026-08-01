package model

import (
	"errors"
	"regexp"
	"strings"
	"time"
)

var canonicalDigest = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

type Report struct {
	InstanceID            string    `json:"instanceId"`
	Environment           string    `json:"environment"`
	Cluster               string    `json:"cluster"`
	Service               string    `json:"service"`
	ConfigVersion         string    `json:"configVersion,omitempty"`
	ImageVersion          string    `json:"imageVersion,omitempty"`
	ReleaseManifestDigest string    `json:"releaseManifestDigest"`
	DesiredHash           string    `json:"desiredHash"`
	EffectiveHash         string    `json:"effectiveHash"`
	InSync                bool      `json:"inSync"`
	Source                string    `json:"source,omitempty"`
	UpdatedAt             time.Time `json:"updatedAt"`
	LastError             string    `json:"lastError,omitempty"`
}

func New(report Report, trustedService, trustedEnvironment, candidateDigest, desiredHash string, now time.Time) (Report, error) {
	report.InstanceID = strings.TrimSpace(report.InstanceID)
	report.Service = strings.TrimSpace(report.Service)
	report.Environment = strings.TrimSpace(report.Environment)
	if report.InstanceID == "" || report.Service != strings.TrimSpace(trustedService) || report.Environment != strings.TrimSpace(trustedEnvironment) {
		return Report{}, errors.New("config instance report identity differs from its trusted principal")
	}
	if !strings.HasPrefix(report.InstanceID, report.Service+"-") {
		return Report{}, errors.New("config instance id is outside the service namespace")
	}
	if !canonicalDigest.MatchString(candidateDigest) || report.ReleaseManifestDigest != candidateDigest {
		return Report{}, errors.New("release manifest digest differs from the current candidate")
	}
	if strings.TrimSpace(desiredHash) == "" || strings.TrimSpace(report.EffectiveHash) == "" {
		return Report{}, errors.New("desiredHash and effectiveHash are required")
	}
	if report.DesiredHash != "" && report.DesiredHash != desiredHash {
		return Report{}, errors.New("reported desiredHash differs from ConfigSnapshot")
	}
	if report.Environment == "prod" && (report.Source != "config-center" || strings.TrimSpace(report.ConfigVersion) == "") {
		return Report{}, errors.New("prod report requires config-center source and configVersion")
	}
	report.ReleaseManifestDigest = candidateDigest
	report.DesiredHash = desiredHash
	report.InSync = desiredHash == report.EffectiveHash
	report.UpdatedAt = now.UTC()
	return report, nil
}
