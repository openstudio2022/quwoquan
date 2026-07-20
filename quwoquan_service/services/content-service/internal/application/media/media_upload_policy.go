package media

import (
	"encoding/hex"
	"fmt"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

func validateInitMediaUploadCommand(command InitMediaUploadCommand) error {
	command = normalizeInitMediaUploadCommand(command)
	mediaType := command.MediaType
	contentType := command.ContentType
	if strings.TrimSpace(command.OwnerID) == "" ||
		command.FileSize <= 0 ||
		!validUploadSHA256(command.ExpectedSHA256) {
		return contentgenerated.AppErrorFromInvalidArgument(
			"media upload requires owner, positive fileSize and SHA-256",
		)
	}
	policy, ok := contentgenerated.ContentMediaUploadPolicies[mediaType]
	if !ok || !contentTypeAllowed(policy.AllowedContentTypes, contentType) {
		return contentgenerated.AppErrorFromMediaTypeUnsupported(
			fmt.Sprintf(
				"mediaType=%q contentType=%q is not allowed",
				mediaType,
				contentType,
			),
		).WithContextAttributes(
			rterr.RuntimeErrorContextAttribute{Key: "mediaType", Value: mediaType},
			rterr.RuntimeErrorContextAttribute{Key: "contentType", Value: contentType},
		)
	}
	if command.FileSize > policy.MaxFileSizeBytes {
		return contentgenerated.AppErrorFromMediaFileTooLarge(
			fmt.Sprintf(
				"media file size %d exceeds maximum %d for %s",
				command.FileSize,
				policy.MaxFileSizeBytes,
				mediaType,
			),
		).WithContextAttributes(
			rterr.RuntimeErrorContextAttribute{
				Key: "actualBytes", Value: fmt.Sprintf("%d", command.FileSize),
			},
			rterr.RuntimeErrorContextAttribute{
				Key: "limitBytes", Value: fmt.Sprintf("%d", policy.MaxFileSizeBytes),
			},
			rterr.RuntimeErrorContextAttribute{Key: "mediaType", Value: mediaType},
		)
	}
	return nil
}

func normalizeInitMediaUploadCommand(
	command InitMediaUploadCommand,
) InitMediaUploadCommand {
	command.OwnerID = strings.TrimSpace(command.OwnerID)
	command.MediaType = strings.ToLower(strings.TrimSpace(command.MediaType))
	command.ContentType = strings.ToLower(
		strings.TrimSpace(strings.Split(command.ContentType, ";")[0]),
	)
	command.ExpectedSHA256 = strings.ToLower(strings.TrimSpace(command.ExpectedSHA256))
	return command
}

func contentTypeAllowed(allowed map[string]struct{}, contentType string) bool {
	if contentType == "" {
		return false
	}
	if _, wildcard := allowed["*/*"]; wildcard {
		return strings.Contains(contentType, "/")
	}
	_, ok := allowed[contentType]
	return ok
}

func validUploadSHA256(value string) bool {
	normalized := strings.TrimPrefix(
		strings.ToLower(strings.TrimSpace(value)),
		"sha256:",
	)
	if len(normalized) != 64 {
		return false
	}
	_, err := hex.DecodeString(normalized)
	return err == nil
}
