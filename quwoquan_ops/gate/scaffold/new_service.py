#!/usr/bin/env python3
"""Create one contract-owned, object-first service vertical slice.

The service-local contract must exist first. The scaffold creates one real vertical
slice plus the minimal autonomous config/deploy/four-environment boundary. It writes
no registry, compatibility layer, release snapshot, README, or empty placeholder.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


SERVICE_PATTERN = re.compile(r"^[a-z][a-z0-9-]*-service$")
SEGMENT_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def fail(message: str, code: int = 2) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return code


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def go_files(service: str, domain: str, context: str, object_name: str) -> dict[str, str]:
    root_import = f"quwoquan_service/services/{service}/internal/{context}/{object_name}"
    return {
        "domain/object.go": f'''package domain

// Object is the first explicit domain type for {domain}.{context}.{object_name}.
type Object struct {{
\tID string
}}
''',
        "application/service.go": f'''package application

import "{root_import}/domain"

// Service owns use-case orchestration; business invariants stay in domain.
type Service struct{{}}

func NewService() *Service {{ return &Service{{}} }}

func (s *Service) Get(id string) domain.Object {{ return domain.Object{{ID: id}} }}
''',
        "adapters/inbound/http/handler.go": f'''package httpadapter

import (
\t"encoding/json"
\t"net/http"

\t"{root_import}/application"
)

func Handler(service *application.Service) http.Handler {{
\treturn http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {{
\t\tw.Header().Set("Content-Type", "application/json")
\t\t_ = json.NewEncoder(w).Encode(service.Get(r.URL.Query().Get("id")))
\t}})
}}
''',
        "infrastructure/clock.go": '''package infrastructure

import "time"

// Clock is an outbound technical implementation; domain types never import it.
type Clock struct{}

func (Clock) Now() time.Time { return time.Now().UTC() }
''',
        "cmd/api/main.go": f'''package main

import (
\t"log"
\t"net/http"

\thttpadapter "{root_import}/adapters/inbound/http"
\t"{root_import}/application"
)

func main() {{
\tif err := http.ListenAndServe(":8080", httpadapter.Handler(application.NewService())); err != nil {{
\t\tlog.Fatal(err)
\t}}
}}
''',
        f"tests/local_contract/{context}/{object_name}/object__local_contract_test.go": f'''package localcontract

import (
\t"testing"

\t"{root_import}/domain"
)

func TestObjectIdentity(t *testing.T) {{
\tif got := (domain.Object{{ID: "object-1"}}).ID; got != "object-1" {{
\t\tt.Fatalf("unexpected identity %q", got)
\t}}
}}
''',
        f"tests/api_integration/{context}/{object_name}/handler__api_integration_test.go": f'''package apiintegration

import (
\t"net/http/httptest"
\t"testing"

\thttpadapter "{root_import}/adapters/inbound/http"
\t"{root_import}/application"
)

func TestObjectQuery(t *testing.T) {{
\trecorder := httptest.NewRecorder()
\trequest := httptest.NewRequest("GET", "/?id=object-1", nil)
\thttpadapter.Handler(application.NewService()).ServeHTTP(recorder, request)
\tif recorder.Code != 200 {{ t.Fatalf("unexpected status %d", recorder.Code) }}
}}
''',
        "build/Dockerfile": f'''ARG GO_BASE_IMAGE=golang:1.24-bookworm
FROM ${{GO_BASE_IMAGE}} AS builder
WORKDIR /build/quwoquan_service
COPY quwoquan_service/go.mod quwoquan_service/go.sum ./
RUN go mod download
COPY quwoquan_service/ ./
RUN CGO_ENABLED=0 go build -o /out/api ./services/{service}/cmd/api

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=builder /out/api /app/api
USER nonroot:nonroot
ENTRYPOINT ["/app/api"]
''',
    }


def python_files(service: str, domain: str, context: str, object_name: str) -> dict[str, str]:
    object_import = f"internal.{context}.{object_name}"
    return {
        "domain/object.py": '''from dataclasses import dataclass


@dataclass(frozen=True)
class Object:
    identifier: str
''',
        "application/service.py": f'''from {object_import}.domain.object import Object


class Service:
    def get(self, identifier: str) -> Object:
        return Object(identifier=identifier)
''',
        "adapters/inbound/http/handler.py": f'''from {object_import}.application.service import Service


def handle(identifier: str) -> dict[str, str]:
    item = Service().get(identifier)
    return {{"id": item.identifier}}
''',
        "infrastructure/clock.py": '''from datetime import datetime, timezone


def now() -> datetime:
    return datetime.now(timezone.utc)
''',
        "cmd/api/main.py": f'''from {object_import}.adapters.inbound.http.handler import handle


if __name__ == "__main__":
    print(handle("health"))
''',
        f"tests/local_contract/{context}/{object_name}/test_object__local_contract_test.py": f'''from {object_import}.domain.object import Object


def test_object_identity() -> None:
    assert Object(identifier="object-1").identifier == "object-1"
''',
        f"tests/api_integration/{context}/{object_name}/test_handler__api_integration_test.py": f'''from {object_import}.adapters.inbound.http.handler import handle


def test_object_query() -> None:
    assert handle("object-1") == {{"id": "object-1"}}
''',
        "build/Dockerfile": f'''ARG PYTHON_BASE_IMAGE=python:3.13-slim
FROM ${{PYTHON_BASE_IMAGE}}
WORKDIR /app
COPY quwoquan_service/services/{service}/ ./
ENTRYPOINT ["python", "-B", "-m", "cmd.api.main"]
''',
        "pyproject.toml": f'''[project]
name = "{service}"
version = "0.1.0"
requires-python = ">=3.13"

[tool.pytest.ini_options]
cache_dir = "../../../.qwq_output/env/repo/local/tests/cache/pytest/{service}"
''',
    }


def autonomous_service_files(service: str, domain: str, language: str) -> dict[str, str]:
    makefile = (
        f'''SERVICE_ROOT := $(abspath ../..)
SERVICE_PACKAGE := ./services/{service}/...

.PHONY: build test gate
build:
\tcd $(SERVICE_ROOT) && go build ./services/{service}/cmd/...
test:
\tcd $(SERVICE_ROOT) && go test $(SERVICE_PACKAGE) -count=1
gate: build test
'''
        if language == "go"
        else '''.PHONY: build test gate
build:
\tpython -B -c "import ast,pathlib; [ast.parse(p.read_text()) for root in ('cmd','internal') for p in pathlib.Path(root).rglob('*.py')]"
test:
\tPYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider tests
gate: build test
'''
    )
    files = {
        "AGENTS.md": f'''# {service} Agent Guide

本目录是 metadata domain `{domain}` 的自治服务边界；同时遵守仓库根与 `quwoquan_service/AGENTS.md`。

- 先修改 `contracts/`，再校验/codegen；禁止手改 `generated/`。
- 人工源码只放 `internal/<context>/<object>/<layer>`。
- 配置、资源、部署和四环境入口均由本服务自治；环境之间禁止继承。
- 禁止导入其他服务的 `internal` 或 `generated`。
''',
        "Makefile": makefile,
        "config/schema.yaml": f'''description: {service} 自治运行配置定义；环境只维护差异和引用。
configs:
  - key: sys.{service}.service.http.addr
    type: string
    scope: workload
    reload: restart
    rollout: progressive
    sensitive: false
    default: ":8080"
''',
        "deploy/base/kustomization.yaml": '''apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
  - service.yaml
''',
        "deploy/base/deployment.yaml": f'''apiVersion: apps/v1
kind: Deployment
metadata:
  name: {service}
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: {service}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: {service}
    spec:
      containers:
        - name: {service}
          image: quwoquan/{service}:package-required
          ports:
            - name: http
              containerPort: 8080
          envFrom:
            - secretRef:
                name: {service}-runtime-secrets
          volumeMounts:
            - name: runtime-config
              mountPath: /etc/qwq/config/{service}.yaml
              subPath: {service}.yaml
              readOnly: true
      volumes:
        - name: runtime-config
          configMap:
            name: {service}-runtime-config
''',
        "deploy/base/service.yaml": f'''apiVersion: v1
kind: Service
metadata:
  name: {service}
spec:
  selector:
    app.kubernetes.io/name: {service}
  ports:
    - name: http
      port: 8080
      targetPort: http
''',
        "deploy/compose.yaml": f'''services:
  {service}:
    build:
      context: ../../..
      dockerfile: quwoquan_service/services/{service}/build/Dockerfile
    environment:
      SERVICE_NAME: {service}
      APP_ENV: "${{QWQ_COMPOSE_ENV:-alpha}}"
      CONFIG_ROOT: /etc/qwq-config
      CONFIG_VERSION: "${{QWQ_COMPOSE_{service.upper().replace('-', '_')}_CONFIG_VERSION:?config version is required}}"
    volumes:
      - ${{QWQ_COMPOSE_CONFIG_ROOT:?config root is required}}:/etc/qwq-config:ro
    ports:
      - "${{QWQ_COMPOSE_SERVICE_PORT:-8080}}:8080"
''',
    }
    for environment in ("alpha", "beta", "gamma", "prod"):
        files[f"environments/{environment}/config.yaml"] = '''overrides: {}
secretRefs: {}
externalBindings: {}
'''
        files[f"environments/{environment}/deploy/kustomization.yaml"] = f'''apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../../deploy/base
namespace: quwoquan-{environment}
labels:
  - pairs:
      quwoquan.io/environment: {environment}
    includeSelectors: false
'''
    return files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", required=True)
    parser.add_argument("--context", required=True)
    parser.add_argument("--object", dest="object_name", required=True)
    parser.add_argument("--language", required=True, choices=("go", "python"))
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not SERVICE_PATTERN.fullmatch(args.service):
        return fail("SERVICE must match <name>-service using lowercase kebab-case")
    context_parts = args.context.split(".")
    if len(context_parts) != 2 or not all(SEGMENT_PATTERN.fullmatch(part) for part in context_parts):
        return fail("CONTEXT must be <metadata-domain>.<bounded-context>")
    if not SEGMENT_PATTERN.fullmatch(args.object_name):
        return fail("OBJECT must be a lowercase snake_case business object")

    domain, context = context_parts
    if context == args.object_name:
        return fail(
            "bounded context and business object must use distinct, "
            "intention-revealing names"
        )
    services = args.repo_root / "quwoquan_service/services"
    service_root = services / args.service
    contract_root = service_root / "contracts"
    domain_contract = contract_root / "domain.yaml"
    context_contract = contract_root / context / "context.yaml"
    object_contract = contract_root / context / args.object_name / "object.yaml"
    if not domain_contract.is_file():
        return fail(f"service domain contract does not exist: {domain_contract}")
    domain_text = domain_contract.read_text(encoding="utf-8")
    if not re.search(rf"(?m)^domain:\s*{re.escape(domain)}\s*$", domain_text):
        return fail(f"service domain contract does not declare domain: {domain}")
    if not context_contract.is_file():
        return fail(f"service context contract does not exist: {domain}.{context}")
    if not object_contract.is_file():
        return fail(f"service object contract does not exist: {domain}.{context}.{args.object_name}")

    owners: list[str] = []
    for candidate in sorted(path for path in services.iterdir() if path.is_dir()):
        candidate_domain = candidate / "contracts/domain.yaml"
        candidate_source = candidate / "internal" / context / args.object_name
        if not candidate_domain.is_file() or not candidate_source.is_dir():
            continue
        if re.search(
            rf"(?m)^domain:\s*{re.escape(domain)}\s*$",
            candidate_domain.read_text(encoding="utf-8"),
        ):
            owners.append(candidate.name)
    if owners:
        return fail(f"contract object already has source owner: {', '.join(owners)}", 1)

    files = (
        go_files(args.service, domain, context, args.object_name)
        if args.language == "go"
        else python_files(args.service, domain, context, args.object_name)
    )
    files.update(autonomous_service_files(args.service, domain, args.language))
    object_root = service_root / "internal" / context / args.object_name
    try:
        for relative_path, content in files.items():
            target = service_root / relative_path
            if relative_path.split("/", 1)[0] in {
                "domain",
                "application",
                "adapters",
                "infrastructure",
            }:
                target = object_root / relative_path
            write(target, content)
    except OSError as exc:
        return fail(f"cannot create scaffold: {exc}", 1)

    print(f"DONE: {service_root}")
    print("NEXT: run contract codegen, then make verify-service-architecture")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
