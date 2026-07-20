package media

import (
	"errors"
	"testing"

	rterr "quwoquan_service/runtime/errors"
)

const validUploadDigest = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

func TestValidateInitMediaUploadCommandAcceptsCanonicalPostMedia(t *testing.T) {
	for _, command := range []InitMediaUploadCommand{
		{
			OwnerID: "persona-1", MediaType: "image", ContentType: "image/jpeg",
			FileSize: 50 * 1024 * 1024, ExpectedSHA256: validUploadDigest,
		},
		{
			OwnerID: "persona-1", MediaType: "video", ContentType: "video/mp4",
			FileSize: 50 * 1024 * 1024, ExpectedSHA256: validUploadDigest,
		},
	} {
		if err := validateInitMediaUploadCommand(command); err != nil {
			t.Fatalf("canonical media command rejected: %v", err)
		}
	}
}

func TestValidateInitMediaUploadCommandRejectsOversizedMedia(t *testing.T) {
	err := validateInitMediaUploadCommand(InitMediaUploadCommand{
		OwnerID: "persona-1", MediaType: "video", ContentType: "video/mp4",
		FileSize: 50*1024*1024 + 1, ExpectedSHA256: validUploadDigest,
	})
	assertMediaUploadErrorCode(t, err, "CONTENT.USER.media_file_too_large")
}

func TestValidateInitMediaUploadCommandRejectsMismatchedContentType(t *testing.T) {
	err := validateInitMediaUploadCommand(InitMediaUploadCommand{
		OwnerID: "persona-1", MediaType: "video", ContentType: "image/png",
		FileSize: 1024, ExpectedSHA256: validUploadDigest,
	})
	assertMediaUploadErrorCode(t, err, "CONTENT.USER.media_type_unsupported")
}

func TestValidateInitMediaUploadCommandPreservesAudioAndFilePolicies(t *testing.T) {
	for _, command := range []InitMediaUploadCommand{
		{
			OwnerID: "persona-1", MediaType: "audio", ContentType: "audio/mp4",
			FileSize: 10 * 1024 * 1024, ExpectedSHA256: validUploadDigest,
		},
		{
			OwnerID: "persona-1", MediaType: "file", ContentType: "application/pdf",
			FileSize: 100 * 1024 * 1024, ExpectedSHA256: validUploadDigest,
		},
	} {
		if err := validateInitMediaUploadCommand(command); err != nil {
			t.Fatalf("shared media command rejected: %v", err)
		}
	}
}

func assertMediaUploadErrorCode(t *testing.T, err error, want string) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected %s", want)
	}
	var appError *rterr.AppError
	if !errors.As(err, &appError) {
		t.Fatalf("expected Runtime AppError, got %T: %v", err, err)
	}
	if got := appError.Code.String(); got != want {
		t.Fatalf("error code=%q want=%q", got, want)
	}
}
