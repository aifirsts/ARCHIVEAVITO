#!/usr/bin/env python3
"""Publish ``site/public`` to Porkbun Static Hosting over FTPS.

Porkbun Static Hosting accepts uploads via FTP with TLS (FTPS) or through the
"GitHub Connect" integration. This script only needs the Python standard library.

Credentials come from the environment (never from command line history):

    PORKBUN_FTP_HOST   ftp host shown on the static hosting page (e.g. ftp.porkbun.com)
    PORKBUN_FTP_USER   the domain name, e.g. usaforru.shop
    PORKBUN_FTP_PASS   the FTP password from the static hosting page

Usage:

    python deploy/publish_porkbun.py --dry-run      # show what would be uploaded
    python deploy/publish_porkbun.py                # upload site/public -> /
    python deploy/publish_porkbun.py --prune        # also delete remote files
                                                    # that are no longer built

The script fails closed: it refuses to run without credentials, verifies that it
is uploading a finished build (index.html, sitemap.xml, robots.txt) and prints a
per-file summary.
"""

from __future__ import annotations

import argparse
import ftplib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCAL = ROOT / "site" / "public"
REQUIRED_FILES = ("index.html", "sitemap.xml", "robots.txt", "404.html")

# Never upload the audit sources even if somebody points --dir at the repo root.
SKIP_DIRS = {".git", ".venv", "node_modules", "avito_audit", "official_assets", "__pycache__"}
SKIP_SUFFIXES = {".zip", ".py", ".pyc", ".md", ".csv", ".json"}
ALLOWED_JSON = {"assets/images.json", "site.webmanifest"}


def collect(local: Path) -> list[Path]:
    files = []
    for path in sorted(local.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(local)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES and rel.as_posix() not in ALLOWED_JSON:
            continue
        files.append(path)
    return files


def ensure_remote_dir(ftp: ftplib.FTP, remote_dir: str) -> None:
    if remote_dir in ("", "/"):
        return
    current = ""
    for part in remote_dir.strip("/").split("/"):
        current += "/" + part
        try:
            ftp.mkd(current)
        except ftplib.error_perm:
            # already exists — fine
            pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Upload site/public to Porkbun Static Hosting")
    parser.add_argument("--dir", default=str(DEFAULT_LOCAL), help="local directory to upload")
    parser.add_argument("--remote", default="/", help="remote directory (default: /)")
    parser.add_argument("--host", default=os.environ.get("PORKBUN_FTP_HOST", ""))
    parser.add_argument("--user", default=os.environ.get("PORKBUN_FTP_USER", ""))
    parser.add_argument("--password", default=os.environ.get("PORKBUN_FTP_PASS", ""))
    parser.add_argument("--dry-run", action="store_true", help="print the plan, do not upload")
    parser.add_argument("--prune", action="store_true", help="delete remote files that are not in the build")
    args = parser.parse_args(argv)

    local = Path(args.dir).resolve()
    if not local.is_dir():
        print(f"Нет каталога сборки: {local}", file=sys.stderr)
        return 2
    missing = [name for name in REQUIRED_FILES if not (local / name).is_file()]
    if missing:
        print("Сборка неполная, публикация остановлена. Нет файлов: " + ", ".join(missing), file=sys.stderr)
        return 2

    files = collect(local)
    total = sum(path.stat().st_size for path in files)
    print(f"Каталог: {local}")
    print(f"Файлов: {len(files)}, объём: {total / 1024 / 1024:.2f} МБ (лимит Porkbun — 40 МБ на файл)")
    if total > 2 * 1024**3:
        print("Слишком большой объём для тарифа Starter (2 ГБ), проверьте сборку.", file=sys.stderr)
        return 2

    if args.dry_run:
        for path in files:
            rel = path.relative_to(local).as_posix()
            print(f"  {rel}  ({path.stat().st_size} Б)")
        print("\n--dry-run: файлы не отправлялись.")
        return 0

    if not (args.host and args.user and args.password):
        print(
            "Нужны PORKBUN_FTP_HOST, PORKBUN_FTP_USER и PORKBUN_FTP_PASS "
            "(страница Static Hosting → FTP Credentials).",
            file=sys.stderr,
        )
        return 2

    print(f"Подключение к {args.host} как {args.user} (FTPS, TLS обязателен)…")
    ftp = ftplib.FTP_TLS(timeout=60)
    try:
        ftp.connect(args.host, 21)
        ftp.login(args.user, args.password)
        ftp.prot_p()  # encrypt the data channel too
        ftp.set_pasv(True)

        uploaded = 0
        for path in files:
            rel = path.relative_to(local).as_posix()
            remote_dir = "/".join([args.remote.strip("/")] + rel.split("/")[:-1]).strip("/")
            ensure_remote_dir(ftp, remote_dir)
            target = ("/" + remote_dir + "/" + path.name) if remote_dir else "/" + path.name
            with path.open("rb") as handle:
                ftp.storbinary(f"STOR {target}", handle)
            uploaded += 1
            print(f"  ↑ {rel}")
        print(f"Загружено файлов: {uploaded}")

        if args.prune:
            print("Проверка лишних файлов в корне (--prune)…")
            top_level = {path.relative_to(local).parts[0] for path in files}
            removed = 0
            for name in ftp.nlst("/"):
                base = name.rsplit("/", 1)[-1]
                if not base or base in {".", ".."} or base in top_level:
                    continue
                try:
                    ftp.delete(name)
                except ftplib.error_perm:
                    try:
                        ftp.rmd(name)
                    except ftplib.error_perm as error:
                        print(f"  ! не удалён {base}: {error}")
                        continue
                removed += 1
                print(f"  ✕ удалён {base}")
            print(f"Удалено файлов: {removed}")
    except ftplib.all_errors as error:
        print(f"Ошибка FTP: {error}", file=sys.stderr)
        return 1
    finally:
        try:
            ftp.quit()
        except Exception:  # noqa: BLE001 - closing errors must not mask the result
            pass

    print(f"\nГотово. Проверьте https://{args.user}/ и https://{args.user}/sitemap.xml")
    print("SSL-сертификат Porkbun выпускает автоматически после первого успешного запроса к домену.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
