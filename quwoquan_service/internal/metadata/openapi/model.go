package openapi

import "fmt"

type openAPIDocument struct {
	OpenAPI    string                     `yaml:"openapi"`
	Info       openAPIInfo                `yaml:"info"`
	Paths      map[string]openAPIPathItem `yaml:"paths"`
	Components openAPIComponents          `yaml:"components"`
}

type openAPIInfo struct {
	Title   string `yaml:"title"`
	Version string `yaml:"version"`
}

type openAPIComponents struct {
	SecuritySchemes map[string]openAPISchema `yaml:"securitySchemes"`
	Schemas         map[string]openAPISchema `yaml:"schemas"`
}

type openAPIPathItem struct {
	Get    *openAPIOperation `yaml:"get,omitempty"`
	Post   *openAPIOperation `yaml:"post,omitempty"`
	Put    *openAPIOperation `yaml:"put,omitempty"`
	Patch  *openAPIOperation `yaml:"patch,omitempty"`
	Delete *openAPIOperation `yaml:"delete,omitempty"`
}

func (item *openAPIPathItem) set(
	method string,
	operation *openAPIOperation,
) error {
	switch method {
	case "GET":
		item.Get = operation
	case "POST":
		item.Post = operation
	case "PUT":
		item.Put = operation
	case "PATCH":
		item.Patch = operation
	case "DELETE":
		item.Delete = operation
	default:
		return fmt.Errorf("unsupported OpenAPI method %q", method)
	}
	return nil
}

type openAPIOperation struct {
	OperationID          string                     `yaml:"operationId"`
	XContractOperationID string                     `yaml:"x-contract-operation-id"`
	XObjectID            string                     `yaml:"x-object-id"`
	XActor               string                     `yaml:"x-actor"`
	XApplication         openAPIApplicationBinding  `yaml:"x-application"`
	Parameters           []openAPIParameter         `yaml:"parameters,omitempty"`
	RequestBody          *openAPIRequestBody        `yaml:"requestBody,omitempty"`
	Responses            map[string]openAPIResponse `yaml:"responses"`
	Security             []map[string][]string      `yaml:"security,omitempty"`
}

type openAPIApplicationBinding struct {
	Kind           string `yaml:"kind"`
	Facet          string `yaml:"facet,omitempty"`
	Method         string `yaml:"method,omitempty"`
	AggregateOwner string `yaml:"aggregateOwner,omitempty"`
	AppendSink     string `yaml:"appendSink,omitempty"`
	LifecycleOwner string `yaml:"lifecycleOwner,omitempty"`
	SessionOwner   string `yaml:"sessionOwner,omitempty"`
	Reader         string `yaml:"reader,omitempty"`
	Slice          string `yaml:"slice,omitempty"`
}

type openAPIParameter struct {
	Name        string        `yaml:"name"`
	In          string        `yaml:"in"`
	Required    bool          `yaml:"required"`
	Description string        `yaml:"description,omitempty"`
	Schema      openAPISchema `yaml:"schema"`
}

type openAPIRequestBody struct {
	Required bool                        `yaml:"required"`
	Content  map[string]openAPIMediaType `yaml:"content"`
}

type openAPIResponse struct {
	Description string                      `yaml:"description"`
	Content     map[string]openAPIMediaType `yaml:"content,omitempty"`
}

type openAPIMediaType struct {
	Schema openAPISchema `yaml:"schema"`
}

type openAPISchema struct {
	Ref                  string                   `yaml:"$ref,omitempty"`
	Type                 string                   `yaml:"type,omitempty"`
	Description          string                   `yaml:"description,omitempty"`
	Nullable             bool                     `yaml:"nullable,omitempty"`
	Required             []string                 `yaml:"required,omitempty"`
	Properties           map[string]openAPISchema `yaml:"properties,omitempty"`
	Items                *openAPISchema           `yaml:"items,omitempty"`
	XContractEntity      string                   `yaml:"x-contract-entity,omitempty"`
	XContractPlaceholder bool                     `yaml:"x-contract-placeholder,omitempty"`
}
