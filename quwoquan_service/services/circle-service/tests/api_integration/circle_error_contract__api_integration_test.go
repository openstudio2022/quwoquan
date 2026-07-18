package api_integration

import (
	"net/http"
	"testing"
)

func TestGetCircle_NotFound(t *testing.T) {
	defer cleanCollections(t)

	rec := doRequest(t, http.MethodGet, "/circles/nonexistent_id_000", nil)
	if rec.Code != http.StatusNotFound {
		t.Errorf("expected 404, got %d", rec.Code)
	}
}

func TestArchiveCircle_NotFound(t *testing.T) {
	defer cleanCollections(t)

	rec := doRequest(t, http.MethodDelete, "/circles/nonexistent_id_000", nil)
	if rec.Code != http.StatusNotFound {
		t.Errorf("expected 404, got %d", rec.Code)
	}
}

func TestGetFile_NotFound(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "文件不存在测试")

	rec := doRequest(t, http.MethodGet, "/circles/"+circleID+"/files/nonexistent_file", nil)
	if rec.Code != http.StatusNotFound {
		t.Errorf("expected 404, got %d", rec.Code)
	}
}

func TestCreateCircle_MissingName(t *testing.T) {
	defer cleanCollections(t)

	rec := doRequest(t, http.MethodPost, "/circles", map[string]any{
		"category": "interest",
	})
	if rec.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestFileTooLarge(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "大文件测试")

	rec := doRequest(t, http.MethodPost, "/circles/"+circleID+"/files", map[string]any{
		"name":      "huge.bin",
		"fileType":  "file",
		"mimeType":  "application/octet-stream",
		"sizeBytes": 60000000, // 60MB > 50MB limit
	})
	if rec.Code != http.StatusRequestEntityTooLarge {
		t.Errorf("expected 413, got %d: %s", rec.Code, rec.Body.String())
	}
	body := decodeBody(t, rec)
	if body["code"] != "CIRCLE.USER.file_too_large" {
		t.Errorf("expected CIRCLE.USER.file_too_large, got %v", body["code"])
	}
}
