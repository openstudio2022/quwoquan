package domain

import (
	"errors"
	"regexp"
	"strconv"
	"strings"
	"time"
)

var ErrInvalid = errors.New("invalid recovery failure")

var (
	appVersionPattern = regexp.MustCompile(`^v?[0-9]+(?:\.[0-9]+){1,3}(?:[-.][A-Za-z0-9]+)*$`)
	identifierPattern = regexp.MustCompile(`^[A-Za-z0-9_.-]{1,128}$`)
)

// Failure is an immutable, sanitized client recovery observation.
type Failure struct {
	OccurredAt   string `json:"occurredAt"`
	AppVersion   string `json:"appVersion"`
	BuildNumber  string `json:"buildNumber"`
	Platform     string `json:"platform"`
	OSVersion    string `json:"osVersion"`
	DeviceModel  string `json:"deviceModel"`
	ErrorSource  string `json:"errorSource"`
	ErrorType    string `json:"errorType"`
	ErrorMessage string `json:"errorMessage"`
	StackTrace   string `json:"stackTrace"`
}

func (failure Failure) Validate(now time.Time) error {
	occurredAt, occurredErr := time.Parse(time.RFC3339Nano, strings.TrimSpace(failure.OccurredAt))
	build, buildErr := strconv.ParseUint(strings.TrimSpace(failure.BuildNumber), 10, 64)
	now = now.UTC()
	if occurredErr != nil || occurredAt.Before(now.Add(-7*24*time.Hour)) || occurredAt.After(now.Add(5*time.Minute)) ||
		!appVersionPattern.MatchString(strings.TrimSpace(failure.AppVersion)) || buildErr != nil || build == 0 ||
		(failure.Platform != "ios" && failure.Platform != "android") ||
		(failure.ErrorSource != "native" && failure.ErrorSource != "flutter" && failure.ErrorSource != "runtime") ||
		!identifierPattern.MatchString(failure.ErrorType) ||
		failure.OSVersion == "" || len(failure.OSVersion) > 64 ||
		failure.DeviceModel == "" || len(failure.DeviceModel) > 128 ||
		failure.ErrorMessage == "" || len(failure.ErrorMessage) > 2<<10 ||
		failure.StackTrace == "" || len(failure.StackTrace) > 32<<10 {
		return ErrInvalid
	}
	return nil
}
