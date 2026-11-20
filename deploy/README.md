# Запуск на OpenShift

Из корня репозитория собери образ с тегом, доступным кластеру. Уточни у организаторов registry, архитектуру узла и namespace. Подключи учётные данные registry способом, принятым в вашем кластере.

```sh
docker build -f Containerfile -t autonomous-cfo:local .
docker run --rm -p 8080:8080 autonomous-cfo:local
```

В другом терминале проверь `curl -fsS http://localhost:8080/health` и открой страницу. Опубликуй образ в registry под отдельным тегом для текущего коммита и задай его в `APP_IMAGE`. Войдя в командный namespace, запусти раннюю проверку:

```sh
oc process --local -f deploy/openshift-template.yaml -p "APP_IMAGE=${APP_IMAGE}" |
  oc apply -f -
oc rollout status deployment/autonomous-cfo
oc get route autonomous-cfo -o jsonpath='{.spec.host}{"\n"}'
```

Шаблон запускает режим `demo` по умолчанию. `/health` подтверждает готовность веб-процесса. Доступ к модели проверяется отдельным запросом через приложение.

Для финального запуска выбери `CFO_MODE=live` после слияния реализации прогноза и клиента модели. Если endpoint требует токен, создай в нужном namespace Secret `autonomous-cfo-model` с ключом `CFO_MODEL_TOKEN` через консоль OpenShift. Заполни переменные `CFO_MODEL_URL` полным URL inference API и `CFO_MODEL_NAME` именем модели, затем обработай шаблон повторно.

```sh
oc process --local -f deploy/openshift-template.yaml \
  -p "APP_IMAGE=${APP_IMAGE}" -p CFO_MODE=live \
  -p "CFO_MODEL_URL=${CFO_MODEL_URL}" -p "CFO_MODEL_NAME=${CFO_MODEL_NAME}" |
  oc apply -f -
oc rollout status deployment/autonomous-cfo
```

По HTTPS-адресу повтори сценарий из [README](../README.md). Проверь успешный прогноз, сценарий с переносом и ответ модели. Формат URL, тела запроса и авторизации согласуй с организаторами, поскольку он зависит от способа публикации модели. [Шаблоны OpenShift](https://docs.redhat.com/en/documentation/openshift_container_platform/4.20/html/building_applications/creating-applications) · [Вызов MaaS в OpenShift AI](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html/govern_llm_access_with_models-as-a-service/use-models-as-a-service_maas-deploy)
