package servicehost

import (
	"os"
	"strings"
)

const serviceCoreModeEnvironment = "SERVICE_CORE_MODE"

// ModuleEnvironmentValue resolves a module-scoped value in service-core while
// preserving the existing standalone environment contract.
func ModuleEnvironmentValue(module string, key string) string {
	if strings.TrimSpace(os.Getenv(serviceCoreModeEnvironment)) != "1" {
		return os.Getenv(key)
	}
	if key == "SERVICE_NAME" {
		return module
	}
	scopedKey := "SERVICE_CORE_" + environmentToken(module) + "_" + key
	if value := os.Getenv(scopedKey); value != "" {
		return value
	}
	return os.Getenv(key)
}

func environmentToken(value string) string {
	var token strings.Builder
	for _, character := range strings.ToUpper(strings.TrimSpace(value)) {
		switch {
		case character >= 'A' && character <= 'Z':
			token.WriteRune(character)
		case character >= '0' && character <= '9':
			token.WriteRune(character)
		default:
			token.WriteByte('_')
		}
	}
	return token.String()
}
