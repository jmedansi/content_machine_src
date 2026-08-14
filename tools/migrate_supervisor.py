#!/usr/bin/env python3
"""Migration supervisor skeleton: dry-run / apply / rollback

Usage:
  python migrate_supervisor.py --mode dry-run --content-root ./accounts --report report.json
"""

import argparse
import json
import logging
import shutil
import zipfile
from pathlib import Path
from datetime import datetime
import uuid
import sys
import os
import re

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lib import content_io
from lib import db_utils


LOG = logging.getLogger("migrate_supervisor")


def backup_path(target: Path) -> Path:
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    dst = Path("backups")
    dst.mkdir(parents=True, exist_ok=True)
    archive = dst / f"backup_{target.name}_{stamp}.zip"
    return archive


def backup_dirs(paths, archive_path: Path):
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for p in paths:
            p = Path(p)
            if p.exists():
                if p.is_file():
                    zf.write(str(p), arcname=str(p.name))
                else:
                    for f in p.rglob('*'):
                        if f.is_file():
                            zf.write(str(f), arcname=str(f.relative_to(p.parent)))


def scan(content_root: str):
    LOG.info("Scanning %s", content_root)
    items = content_io.scan_accounts(content_root)
    return items


def heuristic_map(items, db_conn):
    """Map scanned items to DB accounts using heuristics"""
    db_accounts = db_utils.get_accounts(db_conn)
    db_by_page_id = {row[2]: row for row in db_accounts if row[2]}  # page_id -> row
    db_by_name = {row[3]: row for row in db_accounts if row[3]}  # name -> row
    mappings = []
    for item in items:
        folder_name = item['account_id']
        meta = item['meta'] or {}
        page_id = meta.get('page_id')
        name = meta.get('name')
        platform = meta.get('platform')
        # Heuristics: exact page_id match, then name match, then folder pattern
        match = None
        score = 0
        if page_id and page_id in db_by_page_id:
            match = db_by_page_id[page_id]
            score = 100
        elif name and name in db_by_name:
            match = db_by_name[name]
            score = 80
        elif re.match(r'acc_\d+', folder_name):
            # Assume numeric id maps to account id
            acc_id = folder_name.replace('acc_', '')
            for row in db_accounts:
                if row[0] == acc_id:
                    match = row
                    score = 60
                    break
        mappings.append({
            'item': item,
            'db_match': match,
            'score': score,
            'suggested_account_id': match[0] if match else str(uuid.uuid4()),
            'suggested_platform': platform or (match[1] if match else 'unknown'),
        })
    return mappings


def apply_migration(mappings, db_conn, content_root: str, limit: int = 0):
    """Apply migration: create accounts, contents, normalize meta.json"""
    applied = 0
    for mapping in mappings:
        if limit > 0 and applied >= limit:
            break
        item = mapping['item']
        account_id = mapping['suggested_account_id']
        platform = mapping['suggested_platform']
        # Create account if not exists
        db_utils.insert_account(db_conn, account_id, platform, meta={'migrated': True})
        # Create content row
        content_id = str(uuid.uuid4())
        folder = item['account_id']
        file_path = item['account_folder']
        meta = item['meta'] or {}
        meta = content_io.ensure_meta_fields(meta, {
            'account_id': account_id,
            'platform': platform,
            'created_at': datetime.now().isoformat(),
        })
        db_utils.insert_content(db_conn, content_id, account_id, platform, folder, file_path, meta, 'written')
        # Normalize meta.json on disk
        meta_path = Path(file_path) / 'meta.json'
        content_io.atomic_write_json(str(meta_path), meta)
        LOG.info("Migrated %s -> account %s", folder, account_id)
        applied += 1
    LOG.info("Applied %d migrations", applied)


def generate_report(items, mappings, out_path: Path):
    out = {
        'summary': {
            'accounts_found': len(items),
            'mappings': len(mappings),
            'generated_at': datetime.now().isoformat() + 'Z'
        },
        'mappings': mappings,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['dry-run', 'apply', 'rollback'], required=True)
    parser.add_argument('--content-root', default='accounts')
    parser.add_argument('--report', default='migration_report.json')
    parser.add_argument('--db-path', default='content_machine.db')
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    db_conn = db_utils.init_db(args.db_path)
    items = scan(args.content_root)
    mappings = heuristic_map(items, db_conn)
    report_path = Path(args.report)
    generate_report(items, mappings, report_path)
    LOG.info("Report written to %s", report_path)

    if args.mode == 'dry-run':
        LOG.info("Dry-run complete. No changes made.")
        return

    if args.mode == 'apply':
        # Backup before apply
        archive = backup_path(Path(args.content_root))
        backup_dirs([args.content_root, args.db_path], archive)
        LOG.info("Backup created: %s", archive)
        # Apply
        apply_migration(mappings, db_conn, args.content_root, args.limit)
        LOG.info("Apply complete.")
        return

    if args.mode == 'rollback':
        # Placeholder: find latest backup and restore
        backup_dir = Path("backups")
        if backup_dir.exists():
            backups = sorted(backup_dir.glob("backup_*.zip"), reverse=True)
            if backups:
                latest = backups[0]
                LOG.info("Restoring from %s", latest)
                with zipfile.ZipFile(latest, 'r') as zf:
                    zf.extractall('.')
                LOG.info("Rollback complete.")
            else:
                LOG.error("No backups found.")
        else:
            LOG.error("No backups directory.")


if __name__ == '__main__':
    main()


if __name__ == '__main__':
    main()
