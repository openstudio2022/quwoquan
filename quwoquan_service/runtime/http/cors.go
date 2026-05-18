package runtimehttp

import (
	"net/http"
	"os"
	"strings"
)

type CORSOptions struct {
	AllowedOrigins    []string
	AllowedMethods    []string
	AllowedHeaders    []string
	AllowCredentials  bool
	ExposeHeaders     []string
}

func DefaultCORSOptions() CORSOptions {
	return CORSOptions{
		AllowedOrigins: []string{
			"http://127.0.0.1:",
			"http://localhost:",
			"https://127.0.0.1:",
			"https://localhost:",
		},
		AllowedMethods: []string{
			http.MethodGet,
			http.MethodPost,
			http.MethodOptions,
		},
		AllowedHeaders: []string{
			"Accept",
			"Authorization",
			"Content-Type",
			"Origin",
			"X-Actor",
			"X-Environment",
			"X-Request-Id",
			"X-Trace-Id",
		},
		ExposeHeaders: []string{
			"X-Request-Id",
			"X-Trace-Id",
		},
	}
}

func CORSOptionsFromEnv() CORSOptions {
	options := DefaultCORSOptions()
	if raw := strings.TrimSpace(os.Getenv("OPS_ALLOWED_ORIGINS")); raw != "" {
		options.AllowedOrigins = append(options.AllowedOrigins, splitCSV(raw)...)
	}
	return options
}

func WithCORS(next http.Handler, options CORSOptions) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := strings.TrimSpace(r.Header.Get("Origin"))
		if origin != "" && isAllowedOrigin(origin, options.AllowedOrigins) {
			w.Header().Set("Access-Control-Allow-Origin", origin)
			w.Header().Add("Vary", "Origin")
			w.Header().Set("Access-Control-Allow-Methods", strings.Join(options.AllowedMethods, ", "))
			w.Header().Set("Access-Control-Allow-Headers", strings.Join(options.AllowedHeaders, ", "))
			if len(options.ExposeHeaders) > 0 {
				w.Header().Set("Access-Control-Expose-Headers", strings.Join(options.ExposeHeaders, ", "))
			}
			if options.AllowCredentials {
				w.Header().Set("Access-Control-Allow-Credentials", "true")
			}
		}
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func isAllowedOrigin(origin string, allowlist []string) bool {
	for _, allowed := range allowlist {
		trimmed := strings.TrimSpace(allowed)
		if trimmed == "" {
			continue
		}
		if strings.HasSuffix(trimmed, ":") {
			if strings.HasPrefix(origin, trimmed) {
				return true
			}
			continue
		}
		if origin == trimmed {
			return true
		}
	}
	return false
}

func splitCSV(raw string) []string {
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		if trimmed := strings.TrimSpace(part); trimmed != "" {
			out = append(out, trimmed)
		}
	}
	return out
}
