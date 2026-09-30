"""Manual cache maintenance with scoped previews and no automatic cleanup."""
import os
import secrets
import stat
import subprocess
import threading
import time
from pathlib import Path


class CacheMaintenance:
    SAFE_CACHE_NAMES = {'thumbnails', 'fontconfig', 'mesa_shader_cache', 'mesa_shader_cache_db'}
    PROTECTED_NAMES = {'uv', 'pnpm', '.pnpm', '.pnpm-store', 'npm', '.npm', 'yarn', '.yarn',
                       'pip', 'pipx', 'pypoetry', 'poetry', 'conda', 'mamba', 'bun', '.bun',
                       'node_modules', 'site-packages', 'dist-packages', '.venv', 'venv',
                       'virtualenvs', 'codex', 'codex-runtimes', 'go-build', 'cargo', '.cargo',
                       'rustup', '.rustup', '.git'}
    DEPENDENCY_MARKERS = {'pyvenv.cfg', 'package.json', 'pnpm-lock.yaml', 'uv.lock',
                          'pyproject.toml', 'package-lock.json', 'yarn.lock', 'bun.lock', 'bun.lockb'}

    @classmethod
    def protected_path(cls, path):
        return any(part.lower() in cls.PROTECTED_NAMES for part in Path(path).parts)

    @classmethod
    def supported_cache_root(cls, root):
        if cls.protected_path(root):
            return False
        if root.name in cls.SAFE_CACHE_NAMES:
            return True
        return (root.name in {'Cache', 'Code Cache', 'GPUCache'}
                and (root.parent.name == 'Default' or root.parent.name.startswith('Profile '))
                and root.parent.parent.name == 'google-chrome')

    def __init__(self, cache_home=None, hdd_root=None):
        self.cache_home = Path(cache_home or os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))).absolute()
        self.hdd_root = Path(hdd_root or '/mnt/data').absolute()
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.previews = {}

    @staticmethod
    def memory_cache_bytes():
        memory = {}
        with open('/proc/meminfo') as source:
            for line in source:
                name, value = line.split(':', 1)
                memory[name] = int(value.split()[0]) * 1024
        return sum(memory.get(name, 0) for name in ('Buffers', 'Cached', 'SReclaimable'))

    def ssd_roots(self):
        roots = [self.cache_home / name for name in
                 ('thumbnails', 'fontconfig', 'mesa_shader_cache', 'mesa_shader_cache_db')]
        chrome = self.cache_home / 'google-chrome'
        if chrome.is_dir() and not chrome.is_symlink():
            for profile in chrome.iterdir():
                if profile.name == 'Default' or profile.name.startswith('Profile '):
                    roots.extend(profile / name for name in ('Cache', 'Code Cache', 'GPUCache'))
        return [root for root in roots if root.is_dir() and root.resolve() == root
                and self.supported_cache_root(root)]

    def info(self):
        return {'token': self.token, 'memoryCacheBytes': self.memory_cache_bytes(),
                'ssdPaths': [str(root) for root in self.ssd_roots()],
                'hddMounted': os.path.ismount(self.hdd_root)}

    def roots_for(self, target, path):
        if target == 'ssd':
            return self.ssd_roots()
        if target != 'hdd':
            raise ValueError('지원하지 않는 정리 대상입니다')
        if not os.path.ismount(self.hdd_root):
            raise ValueError('HDD가 연결되어 있지 않습니다')
        if not isinstance(path, str) or not path.strip():
            raise ValueError('HDD의 캐시 폴더 경로를 입력하세요')
        root = Path(path).absolute()
        if root == self.hdd_root or not root.is_relative_to(self.hdd_root):
            raise ValueError('HDD 안의 캐시 폴더만 지정할 수 있습니다')
        if not self.supported_cache_root(root):
            raise ValueError('썸네일·폰트·Mesa 셰이더·Chrome 캐시 폴더만 지원합니다. 패키지·의존성 폴더와 임의의 cache/tmp 폴더는 제외됩니다')
        if not root.is_dir() or root.resolve() != root:
            raise ValueError('존재하는 실제 폴더를 지정하세요. 심볼릭 링크는 제외됩니다')
        if root.stat().st_dev != self.hdd_root.stat().st_dev:
            raise ValueError('지정한 폴더가 HDD와 다른 파일시스템에 있습니다')
        return [root]

    def preview(self, target, path='', days=7):
        if days not in (0, 7, 30):
            raise ValueError('지원하지 않는 파일 보관 기간입니다')
        if target == 'ram':
            roots, files = [], []
            size = self.memory_cache_bytes()
        else:
            roots = self.roots_for(target, path)
            files = []
            cutoff = time.time() - days * 86400
            started = time.monotonic()
            for index, root in enumerate(roots):
                device = root.stat().st_dev
                for directory, dirs, names, directory_fd in os.fwalk(root, follow_symlinks=False):
                    if self.protected_path(directory) or self.DEPENDENCY_MARKERS.intersection(names):
                        dirs[:] = []
                        continue
                    if time.monotonic() - started > 15:
                        raise ValueError('캐시가 너무 큽니다. 더 작은 폴더를 지정하세요')
                    dirs[:] = [name for name in dirs
                               if name.lower() not in self.PROTECTED_NAMES
                               and not os.path.islink(os.path.join(directory, name))
                               and os.stat(name, dir_fd=directory_fd, follow_symlinks=False).st_dev == device]
                    for name in names:
                        try:
                            entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                        except OSError:
                            continue
                        if not stat.S_ISREG(entry.st_mode) or entry.st_dev != device or entry.st_mtime > cutoff:
                            continue
                        relative = str((Path(directory) / name).relative_to(root))
                        files.append((index, relative, entry.st_size, entry.st_mtime_ns, entry.st_ino, entry.st_dev))
                        if len(files) > 50000:
                            raise ValueError('파일이 너무 많습니다. 더 작은 폴더를 지정하세요')
            size = sum(file[2] for file in files)
        preview_id = secrets.token_urlsafe(24)
        now = time.monotonic()
        with self.lock:
            self.previews = {key: value for key, value in self.previews.items() if now - value['created'] < 600}
            if len(self.previews) >= 8:
                self.previews.pop(next(iter(self.previews)))
            self.previews[preview_id] = {'target': target, 'roots': roots, 'files': files,
                                         'created': now, 'days': days, 'path': path}
        return {'previewId': preview_id, 'target': target, 'fileCount': len(files), 'bytes': size,
                'paths': [str(root) for root in roots], 'days': days}

    @classmethod
    def open_directory(cls, path, cache_root):
        """Open every component without following symlinks."""
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        descriptor = os.open('/', flags)
        current = Path('/')
        try:
            for component in Path(path).parts[1:]:
                child = os.open(component, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
                current /= component
                if current.is_relative_to(cache_root) and cls.DEPENDENCY_MARKERS.intersection(os.listdir(descriptor)):
                    raise OSError('Dependency directory is protected')
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    def execute(self, preview_id):
        with self.lock:
            preview = self.previews.pop(preview_id, None)
        if not preview or time.monotonic() - preview['created'] > 600:
            raise ValueError('미리보기가 만료되었습니다. 정리 대상을 다시 확인하세요')
        if preview['target'] == 'ram':
            before = self.memory_cache_bytes()
            executable = '/usr/sbin/sysctl' if Path('/usr/sbin/sysctl').exists() else '/sbin/sysctl'
            command = [executable, '-w', 'vm.drop_caches=3']
            if os.geteuid() != 0:
                command = ['/usr/bin/sudo', '-n', *command]
            try:
                subprocess.run(command, check=True, capture_output=True, timeout=30)
            except subprocess.CalledProcessError as error:
                raise ValueError('RAM 읽기 캐시 정리에 관리자 권한이 필요합니다') from error
            after = self.memory_cache_bytes()
            return {'target': 'ram', 'fileCount': 0, 'beforeBytes': before, 'afterBytes': after,
                    'bytes': max(0, before - after)}
        if preview['target'] == 'hdd':
            # Refuse an unmounted HDD, even if the mount point still exists.
            self.roots_for('hdd', preview['path'])
        removed = freed = skipped = 0
        for index, relative, size, modified, inode, device in preview['files']:
            descriptor = None
            try:
                root = preview['roots'][index]
                if not self.supported_cache_root(root) or self.protected_path(root / relative):
                    skipped += 1
                    continue
                if root.resolve() != root:
                    skipped += 1
                    continue
                descriptor = self.open_directory(root / Path(relative).parent, root)
                if self.DEPENDENCY_MARKERS.intersection(os.listdir(descriptor)):
                    skipped += 1
                    continue
                name = Path(relative).name
                entry = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                identity = (entry.st_size, entry.st_mtime_ns, entry.st_ino, entry.st_dev)
                if not stat.S_ISREG(entry.st_mode) or identity != (size, modified, inode, device):
                    skipped += 1
                    continue
                os.unlink(name, dir_fd=descriptor)
                removed += 1
                freed += size
            except OSError:
                skipped += 1
            finally:
                if descriptor is not None:
                    os.close(descriptor)
        return {'target': preview['target'], 'fileCount': removed, 'bytes': freed, 'skipped': skipped}
