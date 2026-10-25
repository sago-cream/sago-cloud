import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('private_backups', REPO / 'scripts/private-backups.py')
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class PrivateBackupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source'
        self.target = self.root / 'target'
        self.stamp = dt.datetime.now(backup.UTC).strftime('%Y%m%dT%H%M%SZ')
        for directory, prefix in [('sago-media', 'media'), ('minisago-mail', 'mail')]:
            path = self.source / directory / (prefix + '-' + self.stamp + '.sqlite')
            path.parent.mkdir(parents=True)
            with contextlib.closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE credentials (email TEXT PRIMARY KEY, client TEXT NOT NULL, ciphertext TEXT NOT NULL)')
                db.execute("INSERT INTO credentials VALUES ('sample@example.test', 'client', 'encrypted')")
                db.commit()

    def exported(self):
        stream = io.BytesIO()
        backup.export_backups(self.source, stream)
        return stream.getvalue()

    def test_roundtrip_verifies_contents_and_preserves_private_permissions(self):
        self.assertEqual(backup.import_backups(self.exported(), self.target), 2)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o700)
        for path in self.source.glob('*/*.sqlite'):
            copied = self.target / path.relative_to(self.source)
            self.assertEqual(copied.read_bytes(), path.read_bytes())
            self.assertEqual(copied.stat().st_mode & 0o777, 0o600)

    def test_corrupt_transfer_is_rejected_before_publication(self):
        data = self.exported().replace(b'encrypted', b'corrupted', 1)
        with self.assertRaisesRegex(RuntimeError, 'checksum'):
            backup.import_backups(data, self.target)
        self.assertFalse(self.target.exists())

    def test_pending_oauth_tables_are_rejected(self):
        path = next((self.source / 'minisago-mail').glob('*.sqlite'))
        with contextlib.closing(sqlite3.connect(path)) as db:
            db.execute('CREATE TABLE flows (verifier TEXT)')
            db.commit()
        with self.assertRaisesRegex(RuntimeError, 'only encrypted credentials'):
            self.exported()

    def test_missing_or_stale_backups_fail(self):
        path = next((self.source / 'minisago-mail').glob('*.sqlite'))
        path.rename(path.with_name('mail-20200101T000000Z.sqlite'))
        with self.assertRaisesRegex(RuntimeError, 'stale minisago-mail'):
            self.exported()

    def test_expiry_uses_snapshot_date_and_leaves_current_files(self):
        old = self.target / 'sago-media/media-20200101T000000Z.sqlite'
        old.parent.mkdir(parents=True)
        old.write_text('old')
        backup.import_backups(self.exported(), self.target)
        self.assertFalse(old.exists())
        self.assertEqual(len(list(self.target.glob('*/*.sqlite'))), 2)

    def test_archive_paths_cannot_escape_destination(self):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as archive:
            member = tarfile.TarInfo('../outside')
            member.size = 1
            archive.addfile(member, io.BytesIO(b'x'))
        with self.assertRaisesRegex(RuntimeError, 'Unexpected backup archive'):
            backup.import_backups(stream.getvalue(), self.target)
        self.assertFalse((self.root / 'outside').exists())

    def test_mail_snapshot_excludes_sessions_and_preserves_ciphertext(self):
        source = self.root / 'live.sqlite'
        with contextlib.closing(sqlite3.connect(source)) as db:
            db.executescript("CREATE TABLE credentials (email TEXT PRIMARY KEY, client TEXT NOT NULL, ciphertext TEXT NOT NULL);"
                             "INSERT INTO credentials VALUES ('sample@example.test', 'client', 'encrypted');"
                             "CREATE TABLE flows (verifier TEXT); INSERT INTO flows VALUES ('private-session');")
            db.commit()
        script = (REPO / 'scripts/backup-minisago-mail-state').read_text().split("exec -T bot-core bun -e '", 1)[1].split("\n' >", 1)[0]
        data = subprocess.check_output(['bun', '-e', script], env={**os.environ, 'MINISAGO_MAIL_STORE_PATH': str(source)})
        target = self.root / 'mail.sqlite'
        target.write_bytes(data)
        backup.verify_database(target, mail=True)
        with contextlib.closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute('SELECT ciphertext FROM credentials').fetchall(), [('encrypted',)])
        self.assertNotIn(b'private-session', data)


class TailscaleRestoreTests(unittest.TestCase):
    def test_original_profile_and_connection_are_restored_on_success_and_failure(self):
        for originally_running in (True, False):
            for fail in (True, False):
                with self.subTest(running=originally_running, fail=fail):
                    state = {'tailnet': 'NTHUSA', 'running': originally_running}
                    calls = []

                    def run(binary, *args, **kwargs):
                        calls.append((state['tailnet'], args))
                        value = {}
                        if args == ('switch', '--list', '--json'):
                            value = [{'id': name, 'tailnet': name, 'selected': state['tailnet'] == name}
                                     for name in ('NTHUSA', backup.PERSONAL_TAILNET)]
                        elif args == ('debug', 'prefs'):
                            value = {'WantRunning': state['running']}
                        elif args[0] == 'switch':
                            state['tailnet'] = args[1]
                        elif args[0] in ('up', 'down'):
                            state['running'] = args[0] == 'up'
                        elif args == ('status', '--json'):
                            value = {'BackendState': 'Running'}
                        return subprocess.CompletedProcess(args, 0, json.dumps(value).encode(), b'')

                    with patch.object(backup, 'run', side_effect=run):
                        try:
                            with backup.oracle_connection('tailscale'):
                                self.assertEqual(state['tailnet'], backup.PERSONAL_TAILNET)
                                if fail:
                                    raise RuntimeError('transfer failed')
                        except RuntimeError as error:
                            self.assertEqual(str(error), 'transfer failed')
                    self.assertEqual(state, {'tailnet': 'NTHUSA', 'running': originally_running})
                    self.assertEqual([name for name, args in calls if args[0] == 'set'], [backup.PERSONAL_TAILNET])


if __name__ == '__main__':
    unittest.main()
