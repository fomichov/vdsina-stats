"""
vdsina_stats.py — Collect monthly traffic stats for all VDSina servers.

Reads accounts from secrets.yml and writes stats.json + stats.csv.
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

API_BASE = {
    "vdsina.com": "https://userapi.vdsina.com/v1",
    "vdsina.ru":  "https://userapi.vdsina.ru/v1",
}


class VdsinaClient:
    def __init__(self, api_key: str, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {api_key}"})

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self._base_url}/{path.lstrip('/')}"
        response = self._session.get(url, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "ok":
            raise RuntimeError(
                f"API error on {path!r}: {payload.get('status_msg', payload)}"
            )
        return payload

    def list_servers(self) -> list[dict]:
        return self._get("/server")["data"]

    def get_server(self, server_id: int | str) -> dict:
        return self._get(f"/server/{server_id}")["data"]

    def get_server_stat_7d(self, server_id: int | str) -> list[dict]:
        # API ignores date_from/date_to — always returns ~30 days; filter manually.
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        all_stat = self._get(f"/server.stat/{server_id}")["data"]
        return [
            s for s in all_stat
            if datetime.fromisoformat(s["dt"]) >= cutoff.replace(tzinfo=None)
        ]


def bytes_to_gb(value: int | None) -> int | None:
    if value is None:
        return None
    return round(value / (1024 ** 3))


def load_secrets(path: Path) -> list[dict]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("secrets.yml must be a list of account entries")
    for entry in raw:
        if not all(k in entry for k in ("server", "user", "api_key")):
            raise ValueError(f"Each entry must have server, user, api_key — got: {entry}")
    return raw


def collect_stats(client: VdsinaClient, account_server: str, account_user: str) -> list[dict]:  # noqa: E501
    servers = client.list_servers()
    print(f"  Found {len(servers)} server(s).")

    rows = []
    for srv in servers:
        server_id = srv["id"]
        detail = client.get_server(server_id)
        bandwidth = detail.get("bandwidth") or {}

        current_bytes = bandwidth.get("current_month")
        last_bytes = bandwidth.get("last_month")

        traff_data = (detail.get("data") or {}).get("traff") or {}
        plan_traff_bytes = traff_data.get("bytes")

        stat_7d = client.get_server_stat_7d(server_id)
        last_7d_bytes = sum(
            s["stat"]["vnet_rx"] + s["stat"]["vnet_tx"] for s in stat_7d
        ) if stat_7d else None

        row = {
            "account_server": account_server,
            "account_user": account_user,
            "server_id": server_id,
            "server_name": detail.get("name", srv.get("name", "")),
            "plan_traff_bytes": plan_traff_bytes,
            "plan_traff_gb": bytes_to_gb(plan_traff_bytes),
            "current_month_bytes": current_bytes,
            "current_month_gb": bytes_to_gb(current_bytes),
            "last_month_bytes": last_bytes,
            "last_month_gb": bytes_to_gb(last_bytes),
            "last_7d_bytes": last_7d_bytes,
            "last_7d_gb": bytes_to_gb(last_7d_bytes),
        }
        print(
            f"    [{server_id}] {row['server_name']}: "
            f"plan={row['plan_traff_gb']} GB, "
            f"current={row['current_month_gb']} GB, "
            f"last={row['last_month_gb']} GB, "
            f"7d={row['last_7d_gb']} GB"
        )
        rows.append(row)

    return rows


def export_json(rows: list[dict], path: Path) -> None:
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "servers": rows,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"JSON written → {path}")


def export_csv(rows: list[dict], path: Path) -> None:
    fields = [
        "account_server",
        "account_user",
        "server_id",
        "server_name",
        "plan_traff_bytes",
        "plan_traff_gb",
        "current_month_bytes",
        "current_month_gb",
        "last_month_bytes",
        "last_month_gb",
        "last_7d_bytes",
        "last_7d_gb",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV written  → {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect VDSina traffic stats.")
    parser.add_argument(
        "--user",
        metavar="USER",
        help="Only collect stats for accounts matching this user (from secrets.yml).",
    )
    args = parser.parse_args()

    secrets_path = Path(__file__).parent / "secrets.yml"
    if not secrets_path.exists():
        print(f"ERROR: {secrets_path} not found", file=sys.stderr)
        sys.exit(1)

    try:
        accounts = load_secrets(secrets_path)
    except (ValueError, yaml.YAMLError) as exc:
        print(f"ERROR reading secrets.yml: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.user:
        accounts = [a for a in accounts if a["user"] == args.user]
        if not accounts:
            print(f"ERROR: no account found for user {args.user!r}", file=sys.stderr)
            sys.exit(1)

    all_rows: list[dict] = []

    for account in accounts:
        server = account["server"]
        user = account["user"]
        api_key = str(account["api_key"])

        base_url = API_BASE.get(server)
        if not base_url:
            print(f"WARNING: unknown server {server!r}, skipping", file=sys.stderr)
            continue

        print(f"[{server}] {user}")
        client = VdsinaClient(api_key, base_url)

        try:
            rows = collect_stats(client, server, user)
            all_rows.extend(rows)
        except requests.HTTPError as exc:
            print(f"  HTTP error: {exc}", file=sys.stderr)
        except RuntimeError as exc:
            print(f"  API error: {exc}", file=sys.stderr)

    if not all_rows:
        print("No data collected.", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    export_json(all_rows, out_dir / "stats.json")
    export_csv(all_rows, out_dir / "stats.csv")


if __name__ == "__main__":
    main()
