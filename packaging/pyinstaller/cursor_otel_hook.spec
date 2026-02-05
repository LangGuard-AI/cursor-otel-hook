# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for cursor-otel-hook

Builds a single-file executable with all dependencies bundled.
Run with: pyinstaller cursor_otel_hook.spec
"""

import sys
from pathlib import Path

# Get the project root directory
spec_dir = Path(SPECPATH)
project_root = spec_dir.parent.parent

block_cipher = None

# Hidden imports for OpenTelemetry - these are dynamically loaded
hidden_imports = [
    # Core OpenTelemetry
    'opentelemetry',
    'opentelemetry.trace',
    'opentelemetry.context',
    'opentelemetry.baggage',
    'opentelemetry.sdk',
    'opentelemetry.sdk.trace',
    'opentelemetry.sdk.trace.export',
    'opentelemetry.sdk.resources',
    'opentelemetry.sdk._logs',
    'opentelemetry.sdk.metrics',

    # OTLP Exporters
    'opentelemetry.exporter.otlp',
    'opentelemetry.exporter.otlp.proto',
    'opentelemetry.exporter.otlp.proto.common',
    'opentelemetry.exporter.otlp.proto.grpc',
    'opentelemetry.exporter.otlp.proto.grpc.trace_exporter',
    'opentelemetry.exporter.otlp.proto.grpc._log_exporter',
    'opentelemetry.exporter.otlp.proto.http',
    'opentelemetry.exporter.otlp.proto.http.trace_exporter',
    'opentelemetry.exporter.otlp.proto.http._log_exporter',

    # Protocol buffers (used by OTLP)
    'google.protobuf',
    'google.protobuf.descriptor',
    'google.protobuf.message',
    'google.protobuf.reflection',
    'google.protobuf.descriptor_pb2',
    'google.protobuf.any_pb2',
    'google.protobuf.duration_pb2',
    'google.protobuf.timestamp_pb2',
    'google.protobuf.struct_pb2',
    'google.protobuf.wrappers_pb2',

    # gRPC (for gRPC exporter)
    'grpc',
    'grpc._cython',
    'grpc._cython.cygrpc',
    'grpc._channel',
    'grpc._common',
    'grpc._compression',
    'grpc._interceptor',
    'grpc._invocation_defects',
    'grpc._plugin_wrapping',
    'grpc._runtime_protos',
    'grpc._simple_stubs',
    'grpc._utilities',
    'grpc.aio',
    'grpc.beta',
    'grpc.experimental',
    'grpc.framework',

    # Requests (for HTTP exporter)
    'requests',
    'requests.adapters',
    'requests.auth',
    'requests.cookies',
    'requests.models',
    'requests.sessions',
    'urllib3',
    'urllib3.util',
    'urllib3.util.retry',
    'urllib3.util.ssl_',
    'certifi',
    'charset_normalizer',
    'idna',

    # Standard library modules that might be missed
    'logging.handlers',
    'json',
    'hashlib',
    'tempfile',
    'pathlib',
    'argparse',
    'dataclasses',
    're',
    'urllib.parse',
    'http.client',
    'ssl',
    'socket',
    'threading',
    'queue',
    'typing',
    'typing_extensions',
]

# Platform-specific hidden imports
if sys.platform == 'win32':
    hidden_imports.extend([
        'msvcrt',
    ])
else:
    hidden_imports.extend([
        'fcntl',
    ])

a = Analysis(
    [str(project_root / 'src' / 'cursor_otel_hook' / 'hook_receiver.py')],
    pathex=[str(project_root / 'src')],
    binaries=[],
    datas=[],
    hiddenimports=hidden_imports,
    hookspath=[str(spec_dir / 'hooks')],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary modules to reduce size
        'tkinter',
        '_tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'PIL',
        'cv2',
        'scipy',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
        'black',
        'mypy',
        'setuptools',
        'wheel',
        'pip',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='cursor-otel-hook',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,  # Set True for release builds to reduce size
    upx=True,     # Enable UPX compression if available
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Required for stdin/stdout communication with Cursor
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,  # Build for current architecture
    codesign_identity=None,  # For future code signing on macOS
    entitlements_file=None,  # For future macOS hardened runtime
)
