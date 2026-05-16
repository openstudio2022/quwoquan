#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"

echo "[verify] opsx-ff 8-services consistency"

ruby -e '
  root = Dir.pwd
  tasks = File.read(File.join(root, "quwoquan_service/tasks.md"))
  design = File.read(File.join(root, "quwoquan_service/design.md"))
  engineering = File.read(File.join(root, "quwoquan_service/工程目录设计.md"))
  readme = File.read(File.join(root, "quwoquan_service/README.md"))

  services = [
    ["gateway-service", "Gateway 服务", "specs/gateway-service/spec.md"],
    ["orchestrator-service", "Orchestrator 服务", "specs/orchestrator-service/spec.md"],
    ["content-service", "Content 服务", "specs/content-service/spec.md"],
    ["circle-service", "Circle 服务", "specs/circle-service/spec.md"],
    ["user-service", "User 服务", "specs/user-service/spec.md"],
    ["chat-service", "Chat 服务", "specs/chat-service/spec.md"],
    ["assistant-service", "Assistant 服务", "specs/assistant-service/spec.md"],
    ["product-ops", "ProductOps（产品运营）服务", "specs/product-ops/spec.md"]
  ]

  # design baseline check
  unless design.include?("6 个业务单体 + Gateway + Orchestrator")
    abort("[verify] FAIL: design.md missing architecture baseline phrase")
  end

  services.each do |svc, task_title, spec_path|
    spec_file = File.join(root, "quwoquan_service", spec_path)
    abort("[verify] FAIL: missing spec file: #{spec_path}") unless File.file?(spec_file)

    unless engineering.include?("services/#{svc}/")
      abort("[verify] FAIL: engineering directory missing services/#{svc}/")
    end

    unless tasks.include?(task_title)
      abort("[verify] FAIL: tasks.md missing section title: #{task_title}")
    end

    spec_tail = spec_path.sub("specs/", "")
    unless readme.include?(spec_path) || readme.include?(spec_tail)
      abort("[verify] FAIL: README.md missing spec mapping: #{spec_path}")
    end
  end

  puts "[verify] OK: 8 services are aligned in design/tasks/engineering/specs"
'

