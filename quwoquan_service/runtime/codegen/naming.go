package codegen

import "strings"

// CommonAcronyms lists well-known abbreviations that should be fully uppercased in Go names.
var CommonAcronyms = map[string]string{
	"id":    "ID",
	"url":   "URL",
	"ip":    "IP",
	"http":  "HTTP",
	"https": "HTTPS",
	"api":   "API",
	"uri":   "URI",
	"uuid":  "UUID",
	"json":  "JSON",
	"xml":   "XML",
	"sql":   "SQL",
	"html":  "HTML",
	"css":   "CSS",
	"tls":   "TLS",
	"ssl":   "SSL",
	"tcp":   "TCP",
	"udp":   "UDP",
	"dns":   "DNS",
	"ssh":   "SSH",
	"jwt":   "JWT",
	"otp":   "OTP",
	"ttl":   "TTL",
	"rpc":   "RPC",
	"cpu":   "CPU",
	"gpu":   "GPU",
	"os":    "OS",
	"db":    "DB",
	"fk":    "FK",
	"pk":    "PK",
}

// SnakeToGoName converts a snake_case string to a Go PascalCase name with acronym handling.
// Example: "user_id" → "UserID", "avatar_url" → "AvatarURL"
func SnakeToGoName(snake string) string {
	parts := strings.Split(snake, "_")
	var b strings.Builder
	for _, p := range parts {
		if p == "" {
			continue
		}
		if upper, ok := CommonAcronyms[strings.ToLower(p)]; ok {
			b.WriteString(upper)
		} else {
			b.WriteString(strings.ToUpper(p[:1]))
			b.WriteString(p[1:])
		}
	}
	return b.String()
}

// CamelToGoName converts a camelCase string to a Go PascalCase name with acronym handling.
// Example: "userId" → "UserID", "avatarUrl" → "AvatarURL"
func CamelToGoName(camel string) string {
	return SnakeToGoName(CamelToSnake(camel))
}

// CamelToSnake converts a camelCase string to snake_case.
// Example: "userId" → "user_id", "avatarUrl" → "avatar_url"
func CamelToSnake(s string) string {
	var result strings.Builder
	for i, r := range s {
		if r >= 'A' && r <= 'Z' {
			if i > 0 {
				result.WriteByte('_')
			}
			result.WriteRune(r + 32)
		} else {
			result.WriteRune(r)
		}
	}
	return result.String()
}

// SnakeToCamel converts a snake_case string to camelCase.
// Example: "user_id" → "userId", "avatar_url" → "avatarUrl"
func SnakeToCamel(snake string) string {
	parts := strings.Split(snake, "_")
	if len(parts) == 0 {
		return snake
	}
	var b strings.Builder
	b.WriteString(parts[0])
	for _, p := range parts[1:] {
		if len(p) > 0 {
			b.WriteString(strings.ToUpper(p[:1]))
			b.WriteString(p[1:])
		}
	}
	return b.String()
}

// PascalToLowerCamel converts PascalCase to lowerCamelCase.
// Example: "UserProfile" → "userProfile"
func PascalToLowerCamel(s string) string {
	if len(s) == 0 {
		return s
	}
	return strings.ToLower(s[:1]) + s[1:]
}
