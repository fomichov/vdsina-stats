# vdsina-stats

Утилита для сбора статистики трафика по всем серверам VDSina. Поддерживает несколько аккаунтов одновременно (vdsina.com и vdsina.ru). Результаты сохраняются в `output/stats.json` и `output/stats.csv`.

## Что собирается

По каждому серверу:

| Поле | Описание |
|---|---|
| `plan_traff_gb` | Лимит трафика по тарифу (ГБ/месяц) |
| `current_month_gb` | Трафик за текущий месяц (ГБ) |
| `last_month_gb` | Трафик за прошлый месяц (ГБ) |
| `last_7d_gb` | Трафик за последние 7 дней (ГБ) |

Все поля также доступны в байтах (`*_bytes`).

## Установка

```bash
pip install -r requirements.txt
```

## Настройка

Скопируйте `secrets.example.yml` в `secrets.yml` и заполните данные аккаунтов:

```yaml
- server: vdsina.com
  user: user@example.com
  api_key: YOUR_API_TOKEN

- server: vdsina.ru
  user: user@example.com
  api_key: YOUR_API_TOKEN
```

API-токен можно получить в личном кабинете VDSina в разделе настроек пользователя.

`secrets.yml` исключён из git — не коммитьте его.

## Использование

```bash
# Все аккаунты из secrets.yml
python vdsina_stats.py

# Только серверы конкретного пользователя
python vdsina_stats.py --user user@example.com
```

### Результаты

```
output/
  stats.json   — все серверы в виде JSON
  stats.csv    — все серверы в виде CSV
```

## Требования

- Python 3.10+
- Зависимости: `requests`, `pyyaml`
