package auth

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// CollectionQueryBinding 来源：user-service/contracts/account/user_account/fields.yaml。
// 此无密钥 transport 只传递 authority 合同，不持有任何签发逻辑或缓存身份。
type CollectionQueryBinding struct {
	OperationID   string `json:"operationId"`
	CollectionID  string `json:"collectionId"`
	PersistedHash string `json:"persistedHash"`
	BodyDigest    string `json:"bodyDigest"`
	Method        string `json:"method"`
	Path          string `json:"path"`
	Surface       string `json:"surface"`
	RequestID     string `json:"requestId"`
}
type CollectionQueryGrantResult struct {
	Grant              string `json:"grant"`
	ExpiresUnixSeconds int64  `json:"expiresUnixSeconds"`
}
type VerifiedCollectionQueryIdentity struct {
	AccountID          string `json:"accountId"`
	PersonaID          string `json:"personaId"`
	AuthEpoch          int64  `json:"authEpoch"`
	ExpiresUnixSeconds int64  `json:"expiresUnixSeconds"`
}
type CollectionQueryAuthorityClient struct {
	origin                string
	issuePath, verifyPath string
	credentials           ServiceAuthorizationProvider
	client                *http.Client
}

// CollectionAuthorityPaths 由组合根消费生成 operation descriptors 得到，客户端不硬编码 route。
func NewCollectionQueryAuthorityClient(origin, issuePath, verifyPath string, credentials ServiceAuthorizationProvider, client *http.Client) (*CollectionQueryAuthorityClient, error) {
	u, err := url.Parse(origin)
	if err != nil || u.Host == "" || (u.Scheme != "http" && u.Scheme != "https") || u.User != nil || u.RawQuery != "" || u.Fragment != "" || u.Path != "" && u.Path != "/" || credentials == nil || issuePath == "" || verifyPath == "" {
		return nil, errors.New("collection query authority transport incomplete")
	}
	if client == nil {
		return nil, errors.New("collection authority HTTP client required")
	}
	copy := *client
	copy.CheckRedirect = func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	return &CollectionQueryAuthorityClient{strings.TrimRight(origin, "/"), issuePath, verifyPath, credentials, &copy}, nil
}
func (c *CollectionQueryAuthorityClient) Issue(ctx context.Context, source string, binding CollectionQueryBinding) (CollectionQueryGrantResult, error) {
	var out CollectionQueryGrantResult
	err := c.send(ctx, c.issuePath, struct {
		Source  string                 `json:"sourceAccessToken"`
		Binding CollectionQueryBinding `json:"binding"`
	}{source, binding}, &out)
	if err == nil && (out.Grant == "" || out.ExpiresUnixSeconds <= time.Now().Unix()) {
		err = errors.New("authority returned invalid grant")
	}
	return out, err
}
func (c *CollectionQueryAuthorityClient) Verify(ctx context.Context, grant string, binding CollectionQueryBinding) (VerifiedCollectionQueryIdentity, error) {
	var out VerifiedCollectionQueryIdentity
	err := c.send(ctx, c.verifyPath, struct {
		Grant   string                 `json:"grant"`
		Binding CollectionQueryBinding `json:"binding"`
	}{grant, binding}, &out)
	if err == nil && (out.AccountID == "" || out.PersonaID == "" || out.AuthEpoch <= 0 || out.ExpiresUnixSeconds <= time.Now().Unix()) {
		err = errors.New("authority returned invalid identity")
	}
	return out, err
}
func (c *CollectionQueryAuthorityClient) send(ctx context.Context, path string, input, output any) error {
	ctx, cancel := context.WithTimeout(ctx, 800*time.Millisecond)
	defer cancel()
	body, err := json.Marshal(input)
	if err != nil {
		return errors.New("authority request encoding failed")
	}
	r, err := http.NewRequestWithContext(ctx, http.MethodPost, c.origin+path, bytes.NewReader(body))
	if err != nil {
		return errors.New("authority request invalid")
	}
	token, err := c.credentials.AuthorizationHeader(ctx)
	if err != nil {
		return errors.New("authority service credential unavailable")
	}
	r.Header.Set("Authorization", token)
	r.Header.Set("Content-Type", "application/json")
	response, err := c.client.Do(r)
	if err != nil {
		return errors.New("authority request unavailable")
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		return errors.New("authority rejected query delegation")
	}
	raw, err := io.ReadAll(io.LimitReader(response.Body, 32769))
	if err != nil || len(raw) > 32768 {
		return errors.New("authority response invalid")
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if decoder.Decode(output) != nil {
		return errors.New("authority response schema invalid")
	}
	var extra any
	if decoder.Decode(&extra) != io.EOF {
		return errors.New("authority response trailing data")
	}
	return nil
}
