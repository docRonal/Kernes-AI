# Autonomous CFO

Стартовый проект для челленджа Red Hat на Collabothon. Владелец бизнеса загрузит список платежей, увидит кассовый разрыв и проверит, что изменится, если клиент заплатит раньше.

## Запуск на ноутбуке

Установите [uv](https://docs.astral.sh/uv/getting-started/installation/), откройте терминал в корне проекта и выполните:

```sh
uv run --locked uvicorn backend.main:app --host 127.0.0.1 --port 8080
```

Откройте [приложение](http://127.0.0.1:8080) или [Swagger](http://127.0.0.1:8080/docs). Проверки запускаются отдельной командой:

```sh
uv run --locked pytest -q
```

В режиме `demo` программа принимает CSV из [demo/transactions.csv](demo/transactions.csv) и показывает сохранённый ответ. В комплекте есть два ожидаемых исхода и пример ответа модели. Режим `live` содержит точки подключения для расчёта произвольного CSV и вызова OpenShift AI. Развёртывание описано в [deploy/README.md](deploy/README.md).

Для локальных настроек скопируйте `.env.example` в `.env` и передайте `--env-file .env` сразу после `uv run --locked`. По умолчанию приложение запускается в режиме `demo`.

## Первый коммит и ветки

В новый командный GitHub-репозиторий добавьте содержимое этой папки вместе со скрытыми каталогами. Сначала влейте стартовый коммит в `main`, затем создайте ветку для каждого исполнителя и передайте ему промпт из файла роли.

| Инструмент | Ветка | Первый промпт |
| --- | --- | --- |
| Claude Code | `feat/backend` | [Расчёт остатков и API](agents/backend.md) |
| Antigravity | `feat/frontend` | [Интерфейс и проверка в браузере](agents/frontend.md) |
| Codex | `feat/openshift` | [Модель, контейнер и кластер](agents/openshift.md) |

На отдельных ноутбуках каждый работает в своём клоне. Если два агента работают на одном компьютере, откройте их в разных worktree. Например, из основного клона после публикации `main`:

```sh
git fetch origin
git worktree add ../cfo-backend -b feat/backend origin/main
git worktree add ../cfo-frontend -b feat/frontend origin/main
git worktree add ../cfo-openshift -b feat/openshift origin/main
```

Назначьте одного интегратора. Он согласует изменения `contracts/openapi.json`, следит за общими зависимостями и проверяет итоговый `main`. Каждый агент открывает PR со своим diff и результатом локальных проверок. Перед финальной проверкой все подтягивают изменения `main`.

## Инструкции и субагенты

Три основных агента получают правила из [AGENTS.md](AGENTS.md). [CLAUDE.md](CLAUDE.md) подключает его импортом. В каждом инструменте открывайте корень соответствующего клона или worktree.

- `forecast-reviewer` проверяет расчёт, валидацию и сценарий переноса.
- `integration-reviewer` проверяет стыки интерфейса, API и OpenShift.

Конфигурации лежат в `.codex/agents/`, `.claude/agents/` и `.agents/agents/` соответственно. В Codex и Antigravity App/CLI попросите основной агент делегировать ревью по имени и передать список изменённых файлов. В Claude Code можно упомянуть `@agent-forecast-reviewer` или `@agent-integration-reviewer`. Если установленная версия инструмента не показывает субагента, передайте основному агенту [чек-листы ревью](agents/reviewer.md). [Codex](https://learn.chatgpt.com/docs/agent-configuration/subagents#custom-agents) · [Claude Code](https://code.claude.com/docs/en/sub-agents#invoke-subagents-explicitly) · [Antigravity](https://antigravity.google/docs/subagents#custom-subagents)

## Проверка перед демо

1. Откройте приложение по URL OpenShift. Загрузите тестовый CSV, укажите начальный остаток 12 000 PLN и дату начала 23 ноября 2026.
2. Убедитесь, что пятничный остаток 27 ноября равен **−5 000 PLN**.
3. Перенесите платёж `INV-001` на 26 ноября. Убедитесь, что новый пятничный остаток равен **+4 000 PLN**, а базовая линия сохранилась.
4. Запустите объяснение дефицита и проверьте, что запрос дошёл до реальной модели OpenShift AI и вернул объяснение с черновиком письма.
