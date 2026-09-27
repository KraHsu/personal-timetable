import importlib.util
import io
from pathlib import Path
import sqlite3
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('receiver', Path(__file__).resolve().parents[1] / 'deploy/receive.py')
receiver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receiver)
SHA = 'a' * 40


def archive(extra=None, revision=SHA, rust=True):
    stream = io.BytesIO()
    files = {'server.py': b'# Valid Python source\n', 'REVISION': revision.encode()}
    files.update({'public/' + name: b'fixture' for name in receiver.PUBLIC})
    if rust:
        files = {'timetable-server': b'\x7fELF\x02\x01' + b'\x00' * 12 + b'\x3e\x00', 'REVISION': revision.encode()}
        files.update({'public/' + name: b'fixture' for name in ['index.html', 'icon.svg', 'serif.woff2', 'font-license.txt', 'assets/index-test.js', 'assets/index-test.css']})
    with tarfile.open(fileobj=stream, mode='w:gz') as bundle:
        for name, value in files.items():
            item = tarfile.TarInfo(name)
            item.size = len(value)
            bundle.addfile(item, io.BytesIO(value))
        if extra:
            bundle.addfile(extra, io.BytesIO(b'x' * extra.size))
    return stream.getvalue()


class DeployTest(unittest.TestCase):
    def test_command_and_archive_boundaries(self):
        self.assertEqual(receiver.release_id('deploy ' + SHA), SHA)
        for command in ['bash', 'deploy ' + SHA + '; id', 'deploy ../data', 'deploy ' + SHA + '\n']:
            with self.assertRaises(ValueError):
                receiver.release_id(command)
        for name, kind in [('../data/auth.json', tarfile.REGTYPE), ('public/index.html', tarfile.SYMTYPE), ('data/schedule.sqlite3', tarfile.REGTYPE)]:
            item = tarfile.TarInfo(name)
            item.type = kind
            item.linkname = '/etc/passwd'
            with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
                receiver.extract(archive(extra=item), Path(directory), SHA)
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            receiver.extract(archive(revision='b' * 40), Path(directory), SHA)

    def test_rust_binary_permissions_and_legacy_rollback_artifact(self):
        for rust in [True, False]:
            with tempfile.TemporaryDirectory() as directory:
                receiver.extract(archive(rust=rust), Path(directory), SHA)
                if rust:
                    self.assertEqual((Path(directory) / 'timetable-server').stat().st_mode & 0o777, 0o755)

    def exercise(self, succeeds):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            with sqlite3.connect(root / 'data/schedule.sqlite3') as con:
                con.execute('CREATE TABLE courses (name TEXT)')
                con.execute("INSERT INTO courses VALUES ('keep my course')")
            old = root / 'releases' / 'previous'
            old.mkdir(parents=True)
            (old / 'REVISION').write_text('previous')
            (root / 'current').symlink_to(old)
            with patch.object(receiver, 'BASE', root), patch.object(receiver, 'restart') as restart, patch.object(receiver, 'health', side_effect=[True] if succeeds else [False, True]):
                if succeeds:
                    receiver.deploy(archive(), SHA)
                    self.assertEqual((root / 'current').resolve().name, SHA)
                    self.assertEqual(restart.call_count, 1)
                else:
                    with self.assertRaisesRegex(RuntimeError, 'previous release restored'):
                        receiver.deploy(archive(), SHA)
                    self.assertEqual((root / 'current').resolve(), old)
                    self.assertEqual(restart.call_count, 2)
            with sqlite3.connect(root / 'data/schedule.sqlite3') as con:
                self.assertEqual(con.execute('SELECT name FROM courses').fetchone()[0], 'keep my course')
            backup = next((root / 'backups').glob('*.sqlite3'))
            with sqlite3.connect(backup) as con:
                self.assertEqual(con.execute('SELECT name FROM courses').fetchone()[0], 'keep my course')

    def test_success_keeps_data_and_backs_up_database(self):
        self.exercise(True)

    def test_failed_release_rolls_back_without_replacing_data(self):
        self.exercise(False)


if __name__ == '__main__':
    unittest.main()
