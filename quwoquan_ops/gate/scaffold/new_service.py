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
    service_env_prefix = service.upper().replace("-", "_").removesuffix("_SERVICE")
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
        "cmd/api/bootstrap.go": f'''// Package bootstrap 是 {service} 的组合根：本包只声明配置与领域装配，
// 通用启动语义（身份、快照、env 覆盖、观测、auth、基础设施、HTTP 三件套、
// 健康探针、config sync、生命周期）全部由 servicekit 承担（DEC-027/DEC-028）。
package bootstrap

import (
\toperationsecurity "quwoquan_service/generated/operationsecurity"
\t"quwoquan_service/runtime/servicekit"

\thttpadapter "{root_import}/adapters/inbound/http"
\t"{root_import}/application"
)

// config 是 {service} 的声明式运行配置。通用段由内嵌 BaseConfig 提供
// （config.version、service.http.addr、账号安全 authority）。新增基础设施
// 只需在这里声明字段——出现 servicekit.MongoConfig / PostgresConfig /
// RedisSceneConfig 即自动连接、注册健康检查与清理，不要手写连接代码。
type config struct {{
\tservicekit.BaseConfig `yaml:",inline"`
}}

// DeclaredEnvKeys 暴露声明派生的 env 覆盖键全集，供等价断言测试锁定键集
// 不随重构漂移，也供部署面注入键对账。
func DeclaredEnvKeys() ([]string, error) {{
\treturn servicekit.EnvOverrideKeys(
\t\tservicekit.DefaultEnvPrefix("{service}"), &config{{}},
\t)
}}

// NewModule assembles {service} without binding a listener, starting
// workers, admitting traffic, or owning process signals.
func NewModule() (*servicekit.Module, error) {{
\treturn servicekit.Bootstrap("{service}", servicekit.BootstrapSpec[config]{{
\t\tOperationDescriptors: operationsecurity.ForDomain("{domain}"),
\t\tAuthorityScopes:      []string{{"user.account.security.read"}},
\t\tAssemble:             assembleDomain,
\t}})
}}

// assembleDomain 只做领域装配：仓储、用例、路由、worker 与领域健康检查。
// asm 已带好 Mongo/Redis/Postgres/auth/观测/Mux/Workers/Cleanups。
func assembleDomain(asm *servicekit.Assembly, _ *config) error {{
\tasm.Mux.Handle("/", httpadapter.Handler(application.NewService()))
\treturn nil
}}
''',
        "cmd/standalone-api/main.go": f'''package main

import (
\t"quwoquan_service/runtime/servicehost"
\t"quwoquan_service/runtime/servicekit"
\tbootstrap "quwoquan_service/services/{service}/cmd/api"
)

func main() {{
\tservicekit.RunStandalone("{service}", func() (servicehost.Module, error) {{
\t\treturn bootstrap.NewModule()
\t}})
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
RUN CGO_ENABLED=0 go build -o /out/api ./services/{service}/cmd/standalone-api

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
    service_env_prefix = service.upper().replace("-", "_").removesuffix("_SERVICE")
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
- 启动样板不要在本服务重写：`cmd/api/bootstrap.go` 只声明 config 结构与
  `Assemble` 领域装配，身份/快照/env 覆盖/观测/auth/Mongo/Redis/Postgres/
  探针/config sync 由 `runtime/servicekit` 承担（DEC-027/DEC-028）。需要新的
  基础设施就在 config 里声明对应 servicekit 字段，不要手写连接与健康检查。
- `operationsecurity.ForDomain("{domain}")` 为空时启动即失败：先在
  `contracts/**/operations.yaml` 声明 operation 并跑 codegen。
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
  annotations:
    quwoquan.io/config-version: package-required
    quwoquan.io/image-version: package-required
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: {service}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: {service}
      annotations:
        quwoquan.io/config-version: package-required
        quwoquan.io/image-version: package-required
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
          env:
            - name: SERVICE_NAME
              value: {service}
            - name: APP_ENV
              valueFrom:
                fieldRef:
                  fieldPath: metadata.labels['quwoquan.io/environment']
            - name: CONFIG_ROOT
              value: /etc/qwq/config
            - name: CONFIG_VERSION
              valueFrom:
                fieldRef:
                  fieldPath: metadata.annotations['quwoquan.io/config-version']
            - name: IMAGE_VERSION
              valueFrom:
                fieldRef:
                  fieldPath: metadata.annotations['quwoquan.io/image-version']
          volumeMounts:
            - name: runtime-config
              mountPath: /etc/qwq/config/{service}.yaml
              subPath: {service}.yaml
              readOnly: true
          # 探针语义由 servicekit 骨架保证：/healthz 只回答进程存活，
          # /readyz 回答依赖是否就绪。readiness 用 /readyz 才能在依赖抖动时
          # 摘流而不重启；liveness/startup 用 /healthz 才不会因下游抖动误杀。
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
            initialDelaySeconds: 15
            periodSeconds: 20
          startupProbe:
            httpGet:
              path: /healthz
              port: http
            failureThreshold: 30
            periodSeconds: 5
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
    image: "${{QWQ_COMPOSE_{service.upper().replace('-', '_')}_IMAGE:?fixed {service} image reference is required}}"
    build:
      context: ../../..
      dockerfile: quwoquan_service/services/{service}/build/Dockerfile
    environment:
      SERVICE_NAME: {service}
      APP_ENV: "${{QWQ_COMPOSE_ENV:-alpha}}"
      CONFIG_ROOT: /etc/qwq-config
      CONFIG_VERSION: "${{QWQ_COMPOSE_{service.upper().replace('-', '_')}_CONFIG_VERSION:?config version is required}}"
      IMAGE_VERSION: "${{QWQ_COMPOSE_IMAGE_VERSION:?immutable image identity is required}}"
      {service_env_prefix}_SERVICE_ADDR: ":8080"
    volumes:
      - ${{QWQ_COMPOSE_CONFIG_ROOT:?config root is required}}:/etc/qwq-config:ro
    ports:
      - "${{QWQ_COMPOSE_SERVICE_PORT:-8080}}:8080"
    # compose 的 healthy 会被别的服务 depends_on: service_healthy 消费，
    # 所以这里只能探浅层 /healthz；探 /readyz 会在 start_period 窗口内
    # 级联阻塞整条启动链。环境就绪判定用 /readyz。
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://127.0.0.1:8080/healthz >/dev/null 2>&1"]
      interval: 10s
      timeout: 3s
      start_period: 60s
      retries: 10
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
