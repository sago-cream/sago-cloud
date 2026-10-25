#!/usr/bin/env python3
"""Copy private SQLite snapshots over SSH; never publish credentials to Git."""
import contextlib
import datetime as dt
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time

UTC = dt.timezone.utc
RETENTION = dt.timedelta(days=30)
MAX_ARCHIVE = 256 * 1024 * 1024
NAMES = re.compile(r'(sago-media/media|minisago-mail/mail)-([0-9]{8}T[0-9]{6}Z)\.sqlite')
PERSONAL_TAILNET = 'sago-cream.github'
LABEL = 'dev.hsichen.sago-cloud-private-backups'
LOCAL_ROOT = Path.home() / 'Library/Application Support/SagoCloud/backups'


def timestamp(name):
    match = NAMES.fullmatch(name)
    if not match:
        raise RuntimeError('Unexpected backup filename')
    return dt.datetime.strptime(match[2], '%Y%m%dT%H%M%SZ').replace(tzinfo=UTC)


def verify_database(path, mail=False):
    with contextlib.closing(sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise RuntimeError('SQLite backup failed integrity check')
        if mail:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables != {'credentials'}:
                raise RuntimeError('Mail backup must contain only encrypted credentials')
            columns = [row[1] for row in db.execute('PRAGMA table_info(credentials)')]
            if columns != ['email', 'client', 'ciphertext']:
                raise RuntimeError('Unexpected mail credential schema')


def export_backups(root, output):
    now = dt.datetime.now(UTC)
    entries = {}
    for directory in ('sago-media', 'minisago-mail'):
        paths = [path for path in (root / directory).glob('*.sqlite')
                 if NAMES.fullmatch(path.relative_to(root).as_posix())]
        if not paths or max(timestamp(path.relative_to(root).as_posix()) for path in paths) < now - dt.timedelta(hours=48):
            raise RuntimeError('Missing or stale ' + directory + ' backup')
        for path in sorted(paths):
            name = path.relative_to(root).as_posix()
            if timestamp(name) < now - RETENTION:
                continue
            if path.is_symlink():
                raise RuntimeError('Unexpected backup symlink')
            verify_database(path, mail=directory == 'minisago-mail')
            entries[name] = path.read_bytes()
    if sum(map(len, entries.values())) > MAX_ARCHIVE:
        raise RuntimeError('Backup export exceeds size limit')
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in entries.items()}
    with tarfile.open(fileobj=output, mode='w|') as archive:
        for name, data in [('manifest.json', json.dumps(manifest).encode()), *entries.items()]:
            member = tarfile.TarInfo(name)
            member.mode = 0o600
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))


def import_backups(data, root):
    if len(data) > MAX_ARCHIVE:
        raise RuntimeError('Backup transfer exceeds size limit')
    entries = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as archive:
        for member in archive:
            if (not member.isfile() or member.name in entries or member.size > MAX_ARCHIVE
                    or (member.name != 'manifest.json' and not NAMES.fullmatch(member.name))):
                raise RuntimeError('Unexpected backup archive member')
            entries[member.name] = archive.extractfile(member).read()
    if 'manifest.json' not in entries:
        raise RuntimeError('Backup manifest is missing')
    manifest = json.loads(entries.pop('manifest.json'))
    if set(manifest) != set(entries):
        raise RuntimeError('Backup manifest does not match archive')
    now = dt.datetime.now(UTC)
    for directory in ('sago-media', 'minisago-mail'):
        dates = [timestamp(name) for name in entries if name.startswith(directory + '/')]
        if not dates or max(dates) < now - dt.timedelta(hours=48) or max(dates) > now + dt.timedelta(minutes=5):
            raise RuntimeError('Missing or stale ' + directory + ' backup')
    # Validate every file before publishing any of them. Never extract tar paths.
    with tempfile.TemporaryDirectory(prefix='sago-private-') as temporary:
        for index, (name, value) in enumerate(entries.items()):
            if hashlib.sha256(value).hexdigest() != manifest[name]:
                raise RuntimeError('Backup checksum mismatch')
            check = Path(temporary) / str(index)
            check.write_bytes(value)
            check.chmod(0o600)
            verify_database(check, mail=name.startswith('minisago-mail/'))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    for name, value in entries.items():
        target = root / name
        if target.is_symlink() or target.parent.is_symlink():
            raise RuntimeError('Unexpected local backup symlink')
        target.parent.mkdir(mode=0o700, exist_ok=True)
        target.parent.chmod(0o700)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as pending:
            pending.write(value)
            pending.flush()
            os.fsync(pending.fileno())
        os.replace(pending.name, target)
    # Expire by snapshot date, rather than by the date a file was downloaded.
    for directory in ('sago-media', 'minisago-mail'):
        for path in (root / directory).glob('*.sqlite'):
            name = path.relative_to(root).as_posix()
            if NAMES.fullmatch(name) and timestamp(name) < now - RETENTION:
                path.unlink()
    return len(entries)


def run(*args, check=True):
    return subprocess.run(args, check=check, capture_output=True, timeout=120)


def profiles(binary):
    return json.loads(run(binary, 'switch', '--list', '--json').stdout)


def selected_profile(binary):
    return next(profile for profile in profiles(binary) if profile['selected'])


@contextlib.contextmanager
def oracle_connection(binary):
    original = selected_profile(binary)
    running = json.loads(run(binary, 'debug', 'prefs').stdout)['WantRunning']
    personal = next(profile for profile in profiles(binary) if profile['tailnet'] == PERSONAL_TAILNET)
    try:
        if original['id'] != personal['id']:
            run(binary, 'switch', PERSONAL_TAILNET, check=False)
        if selected_profile(binary)['id'] != personal['id']:
            raise RuntimeError('Unable to select personal Tailscale profile')
        # Never change the NTHUSA profile's NAS exit-node preference.
        run(binary, 'set', '--exit-node=')
        run(binary, 'up')
        for _ in range(30):
            if json.loads(run(binary, 'status', '--json').stdout).get('BackendState') == 'Running':
                break
            time.sleep(1)
        else:
            raise RuntimeError('Personal Tailscale profile did not connect')
        yield
    finally:
        # Leave a profile selected by the user during the copy alone.
        if selected_profile(binary)['id'] == personal['id']:
            if original['id'] != personal['id']:
                run(binary, 'switch', original['tailnet'], check=False)
            if selected_profile(binary)['id'] != original['id']:
                raise RuntimeError('Unable to restore original Tailscale profile')
            run(binary, 'up' if running else 'down')


def pull_backups(root=LOCAL_ROOT, force=False):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    with (root / '.pull.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        success = root / 'last-success.json'
        if not force and success.exists():
            completed = dt.datetime.fromisoformat(json.loads(success.read_text())['completedAt'])
            if dt.datetime.now(UTC) - completed < dt.timedelta(hours=24):
                return
        binary = shutil.which('tailscale') or '/usr/local/bin/tailscale'
        with oracle_connection(binary):
            # DNS may settle after the profile connects. Retrying a read-only
            # export is safe and does not create another snapshot or Git commit.
            for attempt in range(4):
                result = run('/usr/bin/ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                             '-o', 'ConnectTimeout=15', 'sago-cloud',
                             'sudo -n python3 /usr/local/libexec/sago-cloud-private-backups export', check=False)
                if result.returncode == 0:
                    break
                if attempt == 3:
                    raise RuntimeError('Oracle backup export failed (SSH exit %s)' % result.returncode)
                time.sleep(3)
            count = import_backups(result.stdout, root)
        temporary = root / 'last-success.pending'
        temporary.write_text(json.dumps({'completedAt': dt.datetime.now(UTC).isoformat(), 'files': count}) + '\n')
        temporary.chmod(0o600)
        os.replace(temporary, success)
        print('Verified and copied %s private database snapshots off Oracle.' % count)


def install_mac():
    if sys.platform != 'darwin':
        raise RuntimeError('Install this LaunchAgent on the recovery Mac')
    application = LOCAL_ROOT.parent
    application.mkdir(parents=True, exist_ok=True, mode=0o700)
    application.chmod(0o700)
    script = application / 'private-backups.py'
    temporary = application / 'private-backups.pending'
    temporary.write_bytes(Path(__file__).read_bytes())
    temporary.chmod(0o700)
    os.replace(temporary, script)
    logs = Path.home() / 'Library/Logs/SagoCloud'
    logs.mkdir(parents=True, exist_ok=True, mode=0o700)
    plist = Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')
    config = {'Label': LABEL, 'ProgramArguments': [shutil.which('python3') or sys.executable, str(script), 'pull'],
              'RunAtLoad': True, 'StartInterval': 3600, 'ProcessType': 'Background', 'Umask': 0o077,
              'EnvironmentVariables': {'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'},
              'StandardOutPath': str(logs / 'private-backups.log'),
              'StandardErrorPath': str(logs / 'private-backups.log')}
    plist.write_bytes(plistlib.dumps(config))
    plist.chmod(0o600)
    domain = 'gui/%s' % os.getuid()
    run('/bin/launchctl', 'bootout', domain + '/' + LABEL, check=False)
    run('/bin/launchctl', 'bootstrap', domain, str(plist))
    print('Installed daily private backup copy with hourly retries while the Mac is awake.')


def main():
    os.umask(0o077)
    command = sys.argv[1:]
    if command == ['export']:
        export_backups(Path('/srv/sago-cloud/backups'), sys.stdout.buffer)
    elif command in (['pull'], ['pull', '--force']):
        pull_backups(force='--force' in command)
    elif command == ['install-mac']:
        install_mac()
    else:
        raise RuntimeError('Usage: private-backups.py export|pull [--force]|install-mac')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, sqlite3.Error, tarfile.TarError) as error:
        print('Private backup failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
