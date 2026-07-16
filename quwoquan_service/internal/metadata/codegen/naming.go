package codegen

import "strings"

var commonAcronyms = map[string]string{
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

func SnakeToGoName(snake string) string {
	parts := strings.Split(snake, "_")
	var result strings.Builder
	for _, part := range parts {
		if part == "" {
			continue
		}
		if upper, exists := commonAcronyms[strings.ToLower(part)]; exists {
			result.WriteString(upper)
			continue
		}
		result.WriteString(strings.ToUpper(part[:1]))
		result.WriteString(part[1:])
	}
	return result.String()
}

func CamelToGoName(camel string) string {
	return SnakeToGoName(CamelToSnake(camel))
}

func CamelToSnake(value string) string {
	var result strings.Builder
	for index, current := range value {
		if current >= 'A' && current <= 'Z' {
			if index > 0 {
				result.WriteByte('_')
			}
			result.WriteRune(current + 32)
			continue
		}
		result.WriteRune(current)
	}
	return result.String()
}

func SnakeToCamel(snake string) string {
	parts := strings.Split(snake, "_")
	if len(parts) == 0 {
		return snake
	}
	var result strings.Builder
	result.WriteString(parts[0])
	for _, part := range parts[1:] {
		if part == "" {
			continue
		}
		result.WriteString(strings.ToUpper(part[:1]))
		result.WriteString(part[1:])
	}
	return result.String()
}

func PascalToLowerCamel(value string) string {
	if value == "" {
		return value
	}
	return strings.ToLower(value[:1]) + value[1:]
}
