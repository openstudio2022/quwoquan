package model

import (
	"errors"
	"regexp"
	"strings"
	"time"
)

var canonicalDigest = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

var (
	ErrInvalidIdentity   = errors.New("config instance report identity is invalid")
	ErrCandidateConflict = errors.New("config instance report candidate conflicts")
	ErrDesiredConflict   = errors.New("config instance report desired hash conflicts")
	ErrInvalidReport     = errors.New("config instance report is invalid")
)

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
		return Report{}, ErrInvalidIdentity
	}
	if !strings.HasPrefix(report.InstanceID, report.Service+"-") {
		return Report{}, ErrInvalidIdentity
	}
	if !canonicalDigest.MatchString(candidateDigest) || report.ReleaseManifestDigest != candidateDigest {
		return Report{}, ErrCandidateConflict
	}
	if strings.TrimSpace(desiredHash) == "" || strings.TrimSpace(report.EffectiveHash) == "" {
		return Report{}, ErrInvalidReport
	}
	if report.DesiredHash != "" && report.DesiredHash != desiredHash {
		return Report{}, ErrDesiredConflict
	}
	if report.Environment == "prod" && (report.Source != "config-center" || strings.TrimSpace(report.ConfigVersion) == "") {
		return Report{}, ErrInvalidReport
	}
	report.ReleaseManifestDigest = candidateDigest
	report.DesiredHash = desiredHash
	report.InSync = desiredHash == report.EffectiveHash
	report.UpdatedAt = now.UTC()
	return report, nil
}
