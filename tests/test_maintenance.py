"""Run with python3 -m unittest discover -s tests. Uses temporary fixtures only."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from maintenance import CacheMaintenance


class DependencyProtectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.cache = self.base / '.cache'
        self.safe = self.cache / 'thumbnails'
        self.safe.mkdir(parents=True)
        self.manager = CacheMaintenance(self.cache, self.base / 'hdd')

    def old_file(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture')
        os.utime(path, (time.time() - 40 * 86400,) * 2)
        return path

    def test_package_caches_and_installed_dependencies_are_preserved(self):
        retained = [self.old_file(self.cache / name / 'dependency.bin')
                    for name in ('uv', 'pnpm', 'npm', 'pip', 'codex-runtimes')]
        retained += [self.old_file(self.safe / name / 'dependency.bin')
                     for name in ('uv', '.pnpm-store', 'node_modules', '.venv', 'site-packages')]
        for marker in self.manager.DEPENDENCY_MARKERS:
            folder = self.safe / ('protected-' + marker)
            retained.extend([self.old_file(folder / marker), self.old_file(folder / 'library.bin')])
        eligible = self.old_file(self.safe / 'normal' / 'thumbnail.png')
        preview = self.manager.preview('ssd', days=0)
        self.assertEqual(preview['fileCount'], 1)
        result = self.manager.execute(preview['previewId'])
        self.assertEqual(result['fileCount'], 1)
        self.assertFalse(eligible.exists())
        self.assertTrue(all(path.exists() for path in retained))

    def test_hdd_only_allows_known_cache_types(self):
        with patch('maintenance.os.path.ismount', return_value=True):
            for relative in ('app-cache', 'tmp', 'uv/thumbnails', 'pnpm/thumbnails', '.venv/fontconfig'):
                root = self.manager.hdd_root / relative
                self.old_file(root / 'important.bin')
                with self.subTest(path=relative), self.assertRaises(ValueError):
                    self.manager.preview('hdd', str(root), days=0)
            root = self.manager.hdd_root / '.cache' / 'thumbnails'
            self.old_file(root / 'thumbnail.png')
            self.assertEqual(self.manager.preview('hdd', str(root), days=0)['fileCount'], 1)

    def test_new_dependency_marker_after_preview_blocks_deletion(self):
        cache_file = self.old_file(self.safe / 'nested' / 'library.bin')
        preview = self.manager.preview('ssd', days=0)
        (cache_file.parent / 'package.json').write_text('{}')
        result = self.manager.execute(preview['previewId'])
        self.assertEqual(result['fileCount'], 0)
        self.assertEqual(result['skipped'], 1)
        self.assertTrue(cache_file.exists())

    def test_ram_reports_before_and_after_without_running_sysctl(self):
        with patch.object(self.manager, 'memory_cache_bytes', side_effect=[1000, 1000, 400]), \
                patch('maintenance.subprocess.run') as command:
            preview = self.manager.preview('ram')
            result = self.manager.execute(preview['previewId'])
        self.assertEqual((result['beforeBytes'], result['afterBytes'], result['bytes']), (1000, 400, 600))
        self.assertEqual(command.call_args.args[0][-2:], ['-w', 'vm.drop_caches=3'])

    def test_new_ancestor_dependency_marker_blocks_deletion(self):
        cache_file = self.old_file(self.safe / 'nested' / 'deeper' / 'library.bin')
        preview = self.manager.preview('ssd', days=0)
        (self.safe / 'pyvenv.cfg').write_text('home = /test')
        result = self.manager.execute(preview['previewId'])
        self.assertEqual(result['fileCount'], 0)
        self.assertTrue(cache_file.exists())


if __name__ == '__main__':
    unittest.main()
