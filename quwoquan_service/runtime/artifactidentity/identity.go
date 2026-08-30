package artifactidentity

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"regexp"
	"strings"
)

const (
	Schema      = "qwq.environment-artifact-identity"
	DefaultPath = "/etc/quwoquan/artifact-identity.json"
)

var digestPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

type Identity struct {
	Schema       string `json:"schema"`
	Environment  string `json:"environment"`
	ConfigDigest string `json:"configDigest"`
}

func LoadAndValidate(path, assertedEnvironment string) (Identity, error) {
	path = strings.TrimSpace(path)
	if path == "" {
		path = DefaultPath
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return Identity{}, fmt.Errorf("read environment artifact identity: %w", err)
	}
	var identity Identity
	decoder := json.NewDecoder(strings.NewReader(string(raw)))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&identity); err != nil {
		return Identity{}, fmt.Errorf("decode environment artifact identity: %w", err)
	}
	if decoder.More() {
		return Identity{}, errors.New("environment artifact identity has trailing values")
	}
	if identity.Schema != Schema {
		return Identity{}, errors.New("environment artifact identity schema mismatch")
	}
	switch identity.Environment {
	case "alpha", "beta", "gamma", "prod":
	default:
		return Identity{}, errors.New("environment artifact identity environment is invalid")
	}
	if !digestPattern.MatchString(identity.ConfigDigest) {
		return Identity{}, errors.New("environment artifact identity config digest is invalid")
	}
	assertedEnvironment = strings.TrimSpace(assertedEnvironment)
	if assertedEnvironment == "" {
		return Identity{}, errors.New("APP_ENV assertion is required during artifact identity cutover")
	}
	if assertedEnvironment != identity.Environment {
		return Identity{}, fmt.Errorf(
			"APP_ENV assertion %q does not match embedded environment %q",
			assertedEnvironment,
			identity.Environment,
		)
	}
	return identity, nil
}
