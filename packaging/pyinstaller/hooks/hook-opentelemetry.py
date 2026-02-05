"""
PyInstaller hook for OpenTelemetry packages.

This hook collects all necessary data files and submodules that are
dynamically imported by OpenTelemetry.
"""

from PyInstaller.utils.hooks import collect_all, collect_submodules

# Initialize collection lists
datas = []
binaries = []
hiddenimports = []

# List of OpenTelemetry packages to fully collect
packages = [
    'opentelemetry',
    'opentelemetry.sdk',
    'opentelemetry.exporter.otlp',
    'opentelemetry.proto',
    'opentelemetry.propagators',
    'opentelemetry.instrumentation',
]

for package in packages:
    try:
        d, b, h = collect_all(package)
        datas.extend(d)
        binaries.extend(b)
        hiddenimports.extend(h)
    except Exception:
        # Package might not be installed, skip it
        pass

# Ensure all submodules are included
submodule_packages = [
    'opentelemetry',
    'opentelemetry.sdk',
    'opentelemetry.exporter',
    'opentelemetry.proto',
    'google.protobuf',
    'grpc',
]

for package in submodule_packages:
    try:
        hiddenimports.extend(collect_submodules(package))
    except Exception:
        pass

# Remove duplicates
hiddenimports = list(set(hiddenimports))
