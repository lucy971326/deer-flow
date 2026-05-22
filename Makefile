# DeerFlow 开发命令

.PHONY: help setup doctor check config config-upgrade install dev dev-daemon start start-daemon stop clean setup-sandbox detect-thread-boundaries docker-init docker-start docker-stop docker-logs docker-logs-frontend docker-logs-gateway up down

PYTHON ?= python3
ifeq ($(OS),Windows_NT)
    PYTHON := python
    RUN_WITH_GIT_BASH := call scripts\run-with-git-bash.cmd
else
    RUN_WITH_GIT_BASH :=
endif

help:
	@echo "  setup        初始化向导"
	@echo "  doctor       系统诊断"
	@echo "  check        检查依赖"
	@echo "  config       生成配置文件"
	@echo "  config-upgrade  合并配置更新"
	@echo "  install      安装前后端依赖 + pre-commit"
	@echo "  dev          启动（开发模式）"
	@echo "  start        启动（生产模式）"
	@echo "  stop         停止所有服务"
	@echo "  clean        清理临时文件"
	@echo "  setup-sandbox  预拉 sandbox 镜像"
	@echo "  docker-*     Docker 开发"
	@echo "  up/down      生产 Docker"

setup:
	@cd backend && uv run python ../scripts/setup_wizard.py

doctor:
	@cd backend && uv run python ../scripts/doctor.py

check:
	@$(PYTHON) ./scripts/check.py

config:
	@$(PYTHON) ./scripts/configure.py

config-upgrade:
	@$(RUN_WITH_GIT_BASH) ./scripts/config-upgrade.sh

detect-thread-boundaries:
	@$(PYTHON) ./scripts/detect_thread_boundaries.py

install:
	@cd backend && uv sync
	@cd frontend && pnpm install
	@pre-commit install
	@echo "✔ 完成"

setup-sandbox:
	@IMAGE=$$(grep -A 20 "# sandbox:" config.yaml 2>/dev/null | grep "image:" | awk '{print $$2}' | head -1); \
	[ -z "$$IMAGE" ] && IMAGE="enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest"; \
	echo "→ $$IMAGE"; \
	command -v container >/dev/null 2>&1 && [ "$$(uname)" = "Darwin" ] && container image pull "$$IMAGE" || true; \
	command -v docker >/dev/null 2>&1 && docker pull "$$IMAGE" || { echo "✗ 未找到 Docker"; exit 1; }

dev: check
	@$(RUN_WITH_GIT_BASH) ./scripts/serve.sh --dev

start: check
	@$(RUN_WITH_GIT_BASH) ./scripts/serve.sh --prod

dev-daemon: check
	@$(RUN_WITH_GIT_BASH) ./scripts/serve.sh --dev --daemon

start-daemon: check
	@$(RUN_WITH_GIT_BASH) ./scripts/serve.sh --prod --daemon

stop:
	@$(RUN_WITH_GIT_BASH) ./scripts/serve.sh --stop

clean: stop
	@rm -rf backend/.deer-flow backend/.langgraph_api logs/*.log 2>/dev/null; true
	@echo "✔ 完成"

docker-init:
	@$(RUN_WITH_GIT_BASH) ./scripts/docker.sh init

docker-start:
	@$(RUN_WITH_GIT_BASH) ./scripts/docker.sh start

docker-stop:
	@$(RUN_WITH_GIT_BASH) ./scripts/docker.sh stop

docker-logs:
	@$(RUN_WITH_GIT_BASH) ./scripts/docker.sh logs

docker-logs-frontend:
	@$(RUN_WITH_GIT_BASH) ./scripts/docker.sh logs --frontend

docker-logs-gateway:
	@$(RUN_WITH_GIT_BASH) ./scripts/docker.sh logs --gateway

up:
	@$(RUN_WITH_GIT_BASH) ./scripts/deploy.sh

down:
	@$(RUN_WITH_GIT_BASH) ./scripts/deploy.sh down
