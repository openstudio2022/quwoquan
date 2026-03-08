package runtimemedia

import (
	"fmt"
	"strings"

	rterr "quwoquan_service/runtime/errors"
)

// UploadPolicy defines constraints for a given category.
type UploadPolicy struct {
	MaxFileSize    int64    // bytes
	AllowedTypes   []string // MIME types, e.g. ["audio/aac", "audio/mp4"]
	MaxDurationMs  int64    // 0 = no limit
	MaxWidth       int      // 0 = no limit
	MaxHeight      int      // 0 = no limit
}

const (
	mb = 1 << 20
	gb = 1 << 30
)

// DefaultPolicies returns the baseline upload policy for each MediaCategory.
func DefaultPolicies() map[MediaCategory]UploadPolicy {
	return map[MediaCategory]UploadPolicy{
		CategoryChatVoice: {
			MaxFileSize:   10 * mb,
			AllowedTypes:  []string{"audio/aac", "audio/mp4", "audio/x-m4a", "audio/mpeg"},
			MaxDurationMs: 120_000,
		},
		CategoryChatImage: {
			MaxFileSize:  20 * mb,
			AllowedTypes: []string{"image/jpeg", "image/png", "image/gif", "image/webp", "image/heic"},
			MaxWidth:     8192,
			MaxHeight:    8192,
		},
		CategoryChatVideo: {
			MaxFileSize:   100 * mb,
			AllowedTypes:  []string{"video/mp4", "video/quicktime"},
			MaxDurationMs: 300_000,
		},
		CategoryChatFile: {
			MaxFileSize:  100 * mb,
			AllowedTypes: []string{}, // any type
		},
		CategoryPost: {
			MaxFileSize:  50 * mb,
			AllowedTypes: []string{"image/jpeg", "image/png", "image/gif", "image/webp", "image/heic", "video/mp4", "video/quicktime"},
		},
		CategoryAvatar: {
			MaxFileSize:  5 * mb,
			AllowedTypes: []string{"image/jpeg", "image/png", "image/webp"},
			MaxWidth:     2048,
			MaxHeight:    2048,
		},
		CategoryCircle: {
			MaxFileSize:  50 * mb,
			AllowedTypes: []string{"image/jpeg", "image/png", "image/gif", "image/webp", "video/mp4"},
		},
	}
}

// ValidateUpload checks the upload request against the policy for its category.
// Returns nil if valid, or an AppError if the upload violates a constraint.
func ValidateUpload(opts InitUploadOpts) error {
	policies := DefaultPolicies()
	policy, ok := policies[opts.Category]
	if !ok {
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"不支持的媒体类别",
			fmt.Sprintf("unknown media category: %s", opts.Category),
		)
	}

	if opts.FileSize > policy.MaxFileSize {
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			fmt.Sprintf("文件大小超过限制（最大 %d MB）", policy.MaxFileSize/mb),
			fmt.Sprintf("file size %d exceeds max %d for category %s", opts.FileSize, policy.MaxFileSize, opts.Category),
		)
	}

	if len(policy.AllowedTypes) > 0 && !containsType(policy.AllowedTypes, opts.ContentType) {
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"不支持的文件类型",
			fmt.Sprintf("content type %s not allowed for category %s; allowed: %v", opts.ContentType, opts.Category, policy.AllowedTypes),
		)
	}

	return nil
}

func containsType(allowed []string, contentType string) bool {
	ct := strings.ToLower(strings.TrimSpace(contentType))
	for _, a := range allowed {
		if strings.ToLower(a) == ct {
			return true
		}
	}
	return false
}
