package skillcontext

import "strings"

func stringMapValue(value map[string]any, key string) string {
	raw, _ := value[key].(string)
	return strings.TrimSpace(raw)
}
