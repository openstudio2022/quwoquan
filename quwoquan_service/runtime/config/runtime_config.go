package runtimeconfig

import (
	"os"
	"strconv"
	"strings"
	"time"
)

type RuntimeConfigProvider interface {
	GetString(key string) (string, bool)
	GetInt(key string) (int, bool)
	GetDurationMs(key string) (time.Duration, bool)
	GetIntList(key string) ([]int, bool)
}

type EnvRuntimeConfigProvider struct{}

func (EnvRuntimeConfigProvider) GetString(key string) (string, bool) {
	v := strings.TrimSpace(os.Getenv(key))
	if v == "" {
		return "", false
	}
	return v, true
}

func (p EnvRuntimeConfigProvider) GetInt(key string) (int, bool) {
	v, ok := p.GetString(key)
	if !ok {
		return 0, false
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return 0, false
	}
	return n, true
}

func (p EnvRuntimeConfigProvider) GetDurationMs(key string) (time.Duration, bool) {
	n, ok := p.GetInt(key)
	if !ok || n <= 0 {
		return 0, false
	}
	return time.Duration(n) * time.Millisecond, true
}

func (p EnvRuntimeConfigProvider) GetIntList(key string) ([]int, bool) {
	v, ok := p.GetString(key)
	if !ok {
		return nil, false
	}
	parts := strings.Split(v, ",")
	result := make([]int, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		n, err := strconv.Atoi(part)
		if err != nil {
			return nil, false
		}
		result = append(result, n)
	}
	if len(result) == 0 {
		return nil, false
	}
	return result, true
}

type MapRuntimeConfigProvider struct {
	Values map[string]string
}

func (p MapRuntimeConfigProvider) GetString(key string) (string, bool) {
	if p.Values == nil {
		return "", false
	}
	v := strings.TrimSpace(p.Values[key])
	if v == "" {
		return "", false
	}
	return v, true
}

func (p MapRuntimeConfigProvider) GetInt(key string) (int, bool) {
	v, ok := p.GetString(key)
	if !ok {
		return 0, false
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return 0, false
	}
	return n, true
}

func (p MapRuntimeConfigProvider) GetDurationMs(key string) (time.Duration, bool) {
	n, ok := p.GetInt(key)
	if !ok || n <= 0 {
		return 0, false
	}
	return time.Duration(n) * time.Millisecond, true
}

func (p MapRuntimeConfigProvider) GetIntList(key string) ([]int, bool) {
	v, ok := p.GetString(key)
	if !ok {
		return nil, false
	}
	parts := strings.Split(v, ",")
	result := make([]int, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		n, err := strconv.Atoi(part)
		if err != nil {
			return nil, false
		}
		result = append(result, n)
	}
	if len(result) == 0 {
		return nil, false
	}
	return result, true
}
