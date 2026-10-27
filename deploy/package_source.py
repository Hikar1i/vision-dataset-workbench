#!/usr/bin/env python3
"""Package the current deployment sources using only the Python standard library."""
import argparse
import hashlib
import io
from pathlib import Path
import stat
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    'Dockerfile', 'compose.yaml', 'compose.gpu.yaml', '.env.example', '.dockerignore',
    'README.md', 'deploy/nginx.conf', 'deploy/worker.py',
    'deploy/agent-deployment.md', 'deploy/package_source.py',
    'backend/pyproject.toml', 'backend/uv.lock', 'backend/alembic.ini',
    'frontend/package.json', 'frontend/package-lock.json', 'frontend/index.html',
    'frontend/tsconfig.json', 'frontend/tsconfig.app.json',
    'frontend/tsconfig.node.json', 'frontend/vite.config.ts',
)
TREES = {
    'backend/src': {'.py'},
    'backend/alembic': {'.py', '.mako'},
    'frontend/src': {'.vue', '.ts', '.js', '.json', '.css', '.svg', '.png', '.jpg', '.woff2'},
    'frontend/public': {'.svg', '.png', '.ico'},
    'project-docs': {'.md'},
}
SKIP = {'.git', '.ai-local', '.env', 'node_modules', '.venv', '__pycache__',
        'tests', 'test-results', 'coverage', 'dist'}


def no_symlinks(path):
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f'Refusing symbolic link: {part}')


def source_files(root):
    selected = set()
    for name in FILES:
        path = root / name
        no_symlinks(path)
        if not path.is_file():
            raise ValueError(f'Missing required source: {name}')
        selected.add(path)

    def walk(directory, suffixes):
        no_symlinks(directory)
        for path in sorted(directory.iterdir()):
            no_symlinks(path)
            if path.name in SKIP or path.name.startswith('.'):
                continue
            if path.is_dir():
                walk(path, suffixes)
            elif not stat.S_ISREG(path.stat().st_mode):
                raise ValueError(f'Refusing non-regular source: {path}')
            elif path.suffix in suffixes and not path.name.endswith(('.spec.ts', '.test.ts')):
                selected.add(path)

    for name, suffixes in TREES.items():
        walk(root / name, suffixes)
    return sorted(selected)


def package(root, output):
    root = root.absolute()
    output = output.absolute()
    checksum = output.with_name(output.name + '.sha256')
    no_symlinks(output)
    no_symlinks(checksum)
    paths = source_files(root)
    if output in paths or checksum in paths:
        raise ValueError('Output must not be a whitelisted source file')
    if not output.name.endswith('.tar.gz'):
        raise ValueError('Output must end in .tar.gz')
    if output.exists() or checksum.exists():
        raise ValueError('Output/checksum already exists; choose a new path')
    output.parent.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        with output.open('xb') as stream:
            created.append(output)
            with tarfile.open(fileobj=stream, mode='w:gz') as archive:
                manifest = []
                for path in paths:
                    no_symlinks(path)
                    if not stat.S_ISREG(path.stat().st_mode):
                        raise ValueError(f'Refusing non-regular source: {path}')
                    data = path.read_bytes()
                    name = path.relative_to(root).as_posix()
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    info.mode = 0o644
                    archive.addfile(info, io.BytesIO(data))
                    manifest.append(f'{hashlib.sha256(data).hexdigest()}  {name}\n')
                data = ''.join(manifest).encode()
                info = tarfile.TarInfo('SHA256SUMS')
                info.size = len(data)
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(data))
        with output.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        with checksum.open('x', encoding='utf-8') as stream:
            created.append(checksum)
            stream.write(f'{digest}  {output.name}\n')
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return digest, len(paths)


def selfcheck():
    # A synthetic tree checks dirty/untracked files without touching repository sources.
    with tempfile.TemporaryDirectory(prefix='vdw-package-') as temporary:
        root = Path(temporary)
        for name in FILES:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('current working tree\n')
        for name in TREES:
            (root / name).mkdir(parents=True, exist_ok=True)
        fresh = root / 'backend/src/uncommitted.py'
        fresh.write_text('uncommitted = True\n')
        for name in ('.env', '.ai-local/secret.txt', 'frontend/node_modules/secret.js',
                     'backend/src/__pycache__/secret.py', 'frontend/src/test.spec.ts',
                     'backend/src/customer.db', 'frontend/dist/result.js'):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('excluded')
        output = root / 'delivery.tar.gz'
        digest, count = package(root, output)
        with tarfile.open(output) as archive:
            names = archive.getnames()
            assert 'backend/src/uncommitted.py' in names
            assert len(names) == count + 1
            assert '.env' not in names
            assert not any(set(Path(name).parts) & SKIP for name in names)
            for line in archive.extractfile('SHA256SUMS').read().decode().splitlines():
                expected, name = line.split('  ', 1)
                assert hashlib.sha256(archive.extractfile(name).read()).hexdigest() == expected
            assert not any('secret' in name or name.endswith(('.db', '.spec.ts', '.tar.gz'))
                           for name in names)
        with output.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == digest
        assert output.with_name(output.name + '.sha256').read_text().startswith(digest)
        for destination in (output, root / 'README.md', root / 'frontend/src/new.ts'):
            try:
                package(root, destination)
            except ValueError:
                pass
            else:
                raise AssertionError('Unsafe output accepted')
        link = root / 'backend/src/link.py'
        link.symlink_to(fresh)
        try:
            package(root, root / 'rejected.tar.gz')
        except ValueError as error:
            assert 'symbolic link' in str(error)
        else:
            raise AssertionError('Symbolic link accepted')
        assert not (root / 'rejected.tar.gz').exists()
    print('PASS: working-tree files, exclusions, manifest/archive SHA256, output protection, symlink rejection; temporary artifacts removed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', nargs='?', type=Path, help='New output path ending in .tar.gz')
    parser.add_argument('--selfcheck', action='store_true', help='Run temporary assert checks only')
    args = parser.parse_args()
    if args.selfcheck:
        if args.output:
            parser.error('--selfcheck takes no output path')
        selfcheck()
    else:
        if args.output is None:
            parser.error('output is required')
        try:
            digest, count = package(ROOT, args.output)
        except (OSError, ValueError) as error:
            parser.exit(1, f'Packaging failed: {error}\n')
        print(f'{args.output.absolute()}\n{count} files\nSHA256 {digest}')


if __name__ == '__main__':
    main()
