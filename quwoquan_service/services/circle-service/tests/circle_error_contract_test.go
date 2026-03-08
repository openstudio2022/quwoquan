package tests

import (
	"net/http"
	"testing"
)

func TestGetCircle_NotFound(t *testing.T) {
	defer cleanCollections(t)

	rec := doRequest(t, http.MethodGet, "/v1/circles/nonexistent_id_000", nil)
	if rec.Code != http.StatusNotFound {
		t.Errorf("expected 404, got %d", rec.Code)
	}
}

func TestJoinCircle_NotFound(t *testing.T) {
	defer cleanCollections(t)

	rec := doRequest(t, http.MethodPost, "/v1/circles/nonexistent_id_000/join", nil)
	if rec.Code != http.StatusNotFound {
		t.Errorf("expected 404, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestLeaveCircle_NotMember(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "非成员退出")

	rec := doRequestAs(t, http.MethodPost, "/v1/circles/"+circleID+"/leave", "user_not_member", nil)
	if rec.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestLeaveCircle_OwnerCannotLeave(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "圈主退出测试")

	rec := doRequest(t, http.MethodPost, "/v1/circles/"+circleID+"/leave", nil)
	if rec.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestArchiveCircle_NotFound(t *testing.T) {
	defer cleanCollections(t)

	rec := doRequest(t, http.MethodDelete, "/v1/circles/nonexistent_id_000", nil)
	if rec.Code != http.StatusNotFound {
		t.Errorf("expected 404, got %d", rec.Code)
	}
}

func TestGetFile_NotFound(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "文件不存在测试")

	rec := doRequest(t, http.MethodGet, "/v1/circles/"+circleID+"/files/nonexistent_file", nil)
	if rec.Code != http.StatusNotFound {
		t.Errorf("expected 404, got %d", rec.Code)
	}
}

func TestCreateCircle_MissingName(t *testing.T) {
	defer cleanCollections(t)

	rec := doRequest(t, http.MethodPost, "/v1/circles", map[string]any{
		"category": "interest",
	})
	if rec.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestFileTooLarge(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "大文件测试")

	rec := doRequest(t, http.MethodPost, "/v1/circles/"+circleID+"/files", map[string]any{
		"name":      "huge.bin",
		"fileType":  "file",
		"mimeType":  "application/octet-stream",
		"sizeBytes": 60000000, // 60MB > 50MB limit
	})
	if rec.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d: %s", rec.Code, rec.Body.String())
	}
}
