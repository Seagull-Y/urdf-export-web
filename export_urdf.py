#!/usr/bin/env python3
"""
Script to export URDF from Onshape using onshape-to-robot
"""

import os
import sys
import json
import time
import argparse
import subprocess
from pathlib import Path
from urllib.parse import urlparse

# Note: onshape-to-robot is primarily used as a command-line tool
# The Python API structure may vary, so we default to using the CLI
HAS_PYTHON_API = False


def parse_onshape_url(url):
    """
    Parse Onshape URL to extract documentId, workspaceId, and elementId.

    Accepts both full URLs and document-only URLs:
      https://cad.onshape.com/documents/{docId}/w/{wsId}/e/{elId}
      https://cad.onshape.com/documents/{docId}/w/{wsId}
      https://cad.onshape.com/documents/{docId}
    Only documentId is required by onshape-to-robot; the others are optional.
    """
    parsed = urlparse(url)
    path_parts = parsed.path.strip('/').split('/')

    try:
        doc_idx = path_parts.index('documents')
        document_id = path_parts[doc_idx + 1]
    except (ValueError, IndexError) as e:
        raise ValueError(f"Invalid Onshape URL — could not find document ID: {url}") from e

    workspace_id = None
    element_id = None
    try:
        ws_idx = path_parts.index('w')
        workspace_id = path_parts[ws_idx + 1]
    except (ValueError, IndexError):
        pass
    try:
        el_idx = path_parts.index('e')
        element_id = path_parts[el_idx + 1]
    except (ValueError, IndexError):
        pass

    return document_id, workspace_id, element_id


def cleanup_export_directory(output_dir):
    """
    Clean up export directory, keeping only .urdf and .stl files
    
    Args:
        output_dir: Output directory to clean
    """
    from pathlib import Path
    
    output_dir = Path(output_dir)
    deleted_count = 0
    
    # Find all files that are not .urdf or .stl
    for file_path in output_dir.rglob('*'):
        if file_path.is_file():
            if not (file_path.suffix.lower() in ['.urdf', '.stl']):
                try:
                    file_path.unlink()
                    deleted_count += 1
                    if deleted_count <= 5:  # Print first few
                        print(f"  Deleted: {file_path.relative_to(output_dir)}")
                except Exception as e:
                    print(f"  Warning: Could not delete {file_path}: {e}")
    
    # Also remove empty directories (except assets if it has STL files)
    for dir_path in sorted(output_dir.rglob('*'), reverse=True):
        if dir_path.is_dir() and dir_path != output_dir:
            try:
                # Check if directory is empty or only contains .stl files
                contents = list(dir_path.iterdir())
                if not contents or all(f.suffix.lower() == '.stl' for f in contents if f.is_file()):
                    # Don't delete if it contains .stl files (like assets/)
                    if not any(f.suffix.lower() == '.stl' for f in contents if f.is_file()):
                        dir_path.rmdir()
            except Exception:
                pass  # Ignore errors when removing directories
    
    if deleted_count > 5:
        print(f"  ... and {deleted_count - 5} more files")
    if deleted_count > 0:
        print(f"  Cleaned up {deleted_count} unnecessary files")


def fix_urdf_mesh_paths(urdf_path, output_dir):
    """
    Fix mesh file paths in URDF to use relative paths from URDF location
    
    Args:
        urdf_path: Path to the URDF file
        output_dir: Output directory containing assets folder
    """
    import re
    from pathlib import Path
    
    urdf_path = Path(urdf_path)
    output_dir = Path(output_dir)
    assets_dir = output_dir / 'assets'
    
    # Read URDF content
    with open(urdf_path, 'r') as f:
        urdf_content = f.read()
    
    # Check if assets directory exists
    if not assets_dir.exists():
        print(f"  Warning: Assets directory not found: {assets_dir}")
        return
    
    # Replace package://assets/ with relative path
    # Option 1: Use relative path (assets/filename.stl) - works if URDF and assets are in same parent dir
    # Option 2: Use absolute path
    # Option 3: Keep package:// but ensure it's correct
    
    # We'll use relative path: assets/filename.stl (relative to URDF file)
    def replace_path(match):
        stl_filename = match.group(1)
        # Use relative path from URDF to assets
        # Since URDF is in output/ and assets is in output/assets/
        # Relative path is: assets/filename.stl
        return f'filename="assets/{stl_filename}"'
    
    # Replace package://assets/ with assets/
    urdf_content_fixed = re.sub(
        r'filename="package://assets/([^"]+)"',
        replace_path,
        urdf_content
    )
    
    # Count replacements
    original_count = len(re.findall(r'package://assets/', urdf_content))
    if original_count > 0:
        print(f"  Fixed {original_count} mesh paths from package://assets/ to assets/")
    
    # Write back
    with open(urdf_path, 'w') as f:
        f.write(urdf_content_fixed)
    
    print(f"  Updated URDF: {urdf_path}")


def get_api_credentials(access_key=None, secret_key=None, credentials_file=None):
    """
    Get Onshape API credentials from various sources (priority order):
    1. Function arguments (if provided)
    2. Environment variables
    3. Credentials file (credentials.json or .env)
    
    Args:
        access_key: Optional access key from command line
        secret_key: Optional secret key from command line
        credentials_file: Optional path to credentials file
    """
    # First, try function arguments
    if access_key and secret_key:
        return access_key, secret_key
    
    # Second, try environment variables
    env_access_key = os.getenv('ONSHAPE_ACCESS_KEY')
    env_secret_key = os.getenv('ONSHAPE_SECRET_KEY')
    if env_access_key and env_secret_key:
        return env_access_key, env_secret_key
    
    # Third, try credentials file
    cred_files = []
    if credentials_file:
        cred_files.append(Path(credentials_file))
    # Also try default credentials.json
    cred_files.append(Path('credentials.json'))
    
    for cred_file in cred_files:
        if cred_file.exists():
            try:
                with open(cred_file, 'r') as f:
                    creds = json.load(f)
                    file_access_key = creds.get('ONSHAPE_ACCESS_KEY') or creds.get('access_key')
                    file_secret_key = creds.get('ONSHAPE_SECRET_KEY') or creds.get('secret_key')
                    if file_access_key and file_secret_key:
                        return file_access_key, file_secret_key
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Warning: Could not read credentials from {cred_file}: {e}")
    
    # Try .env file
    env_file = Path('.env')
    if env_file.exists():
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key == 'ONSHAPE_ACCESS_KEY' and not access_key:
                            access_key = value
                        elif key == 'ONSHAPE_SECRET_KEY' and not secret_key:
                            secret_key = value
            if access_key and secret_key:
                return access_key, secret_key
        except Exception as e:
            print(f"Warning: Could not read .env file: {e}")
    
    # If still not found, raise error
    raise ValueError(
        "Onshape API credentials not found. "
        "Please provide them via:\n"
        "  1. Command line arguments (--access-key and --secret-key)\n"
        "  2. Environment variables (ONSHAPE_ACCESS_KEY and ONSHAPE_SECRET_KEY)\n"
        "  3. Credentials file (credentials.json or .env)"
    )


def _prewarm_cache(output_config_file, document_id, assembly_name, access_key, secret_key):
    """
    Parallel pre-warm the onshape-to-robot file cache for all parts in an assembly.
    Downloads part STL meshes and metadata in parallel using ThreadPoolExecutor,
    writing results to ~/.cache/onshape-to-robot/ so the subsequent serial
    onshape-to-robot run reads from cache instead of making network calls.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    try:
        from onshape_to_robot.onshape_api.client import Client
    except ImportError:
        print("[PREWARM] onshape_to_robot not importable, skipping pre-warm", flush=True)
        return

    # Set env vars in current process so Client can authenticate
    if access_key:
        os.environ['ONSHAPE_ACCESS_KEY'] = access_key
    if secret_key:
        os.environ['ONSHAPE_SECRET_KEY'] = secret_key
    os.environ.setdefault('ONSHAPE_API', 'https://cad.onshape.com')

    creds_path = str(output_config_file)

    # Thread-local Client so each worker thread has its own HTTP session
    _local = threading.local()

    def get_client():
        if not hasattr(_local, 'client'):
            _local.client = Client(logging=False, creds=creds_path)
        return _local.client

    print("[PREWARM] Connecting to Onshape to discover parts...", flush=True)

    # Use a single client for the discovery phase (single-threaded)
    try:
        main_client = Client(logging=False, creds=creds_path)
    except Exception as e:
        print(f"[PREWARM] Could not init client: {e}", flush=True)
        return

    # Resolve workspace ID
    try:
        doc = main_client.get_document(document_id)
        if not doc or "defaultWorkspace" not in doc:
            print("[PREWARM] Unexpected document response, skipping pre-warm", flush=True)
            return
        workspace_id = doc["defaultWorkspace"]["id"]
    except Exception as e:
        msg = str(e)
        if "402" in msg or "limit" in msg.lower():
            print("[PREWARM] Onshape API limit exceeded — skipping pre-warm", flush=True)
        elif "403" in msg or "permission" in msg.lower():
            print("[PREWARM] Onshape API access denied (403) — skipping pre-warm", flush=True)
        else:
            print(f"[PREWARM] Could not get document: {e}", flush=True)
        return

    # Find assembly element ID
    try:
        elements = main_client.list_elements(document_id, workspace_id)
        element_id = None
        for el in elements:
            if el.get("type") == "Assembly":
                if not assembly_name or el.get("name") == assembly_name:
                    element_id = el["id"]
                    break
        if element_id is None:
            for el in elements:
                if el.get("type") == "Assembly":
                    element_id = el["id"]
                    break
        if element_id is None:
            print("[PREWARM] No assembly element found, skipping pre-warm", flush=True)
            return
    except Exception as e:
        print(f"[PREWARM] Could not list elements: {e}", flush=True)
        return

    # Get full assembly structure (uses workspace — not cacheable, but fast)
    try:
        assembly_data = main_client.get_assembly(
            document_id, workspace_id, element_id, wmv="w"
        )
    except Exception as e:
        print(f"[PREWARM] Could not get assembly: {e}", flush=True)
        return

    # Walk instances recursively to collect all part instances
    def collect_parts(instances, sub_assemblies):
        parts = []
        for inst in instances:
            if inst.get("suppressed"):
                continue
            if inst.get("type") == "Part":
                parts.append(inst)
            elif inst.get("type") == "Assembly":
                d = inst["documentId"]
                m = inst.get("documentMicroversion")
                e = inst["elementId"]
                c = inst["configuration"]
                for sub in sub_assemblies:
                    if (sub["documentId"] == d
                            and sub.get("documentMicroversion") == m
                            and sub["elementId"] == e
                            and sub["configuration"] == c):
                        parts.extend(collect_parts(sub["instances"], sub_assemblies))
                        break
        return parts

    all_instances = collect_parts(
        assembly_data["rootAssembly"]["instances"],
        assembly_data.get("subAssemblies", []),
    )

    # Deduplicate by the tuple that uniquely identifies a cached entry
    seen = set()
    unique_parts = []
    for inst in all_instances:
        key = (
            inst["documentId"],
            inst.get("documentMicroversion", inst.get("documentVersion")),
            inst["elementId"],
            inst["configuration"],
            inst.get("partId", ""),
        )
        if key not in seen:
            seen.add(key)
            unique_parts.append(inst)

    total = len(unique_parts)
    if total == 0:
        print("[PREWARM] No parts found, skipping pre-warm", flush=True)
        return

    print(f"[PREWARM] Pre-warming {total} unique parts in parallel (5 workers)...", flush=True)

    done_count = [0]
    fail_count = [0]
    lock = threading.Lock()

    def warm_part(inst):
        # Key insight: kwargs dict ORDER must match instance_request_params() exactly,
        # because pickle.dumps(dict) preserves insertion order, and the cache key is
        # sha1(pickle({args, kwargs})). Mismatched order → different hash → cache miss.
        # instance_request_params builds: wmvid, wmv, did, eid, linked_document_id,
        # configuration — then partid is appended last by the caller.
        if "documentVersion" in inst:
            wmvid = inst["documentVersion"]
            wmv   = "v"
        else:
            wmvid = inst["documentMicroversion"]
            wmv   = "m"
        did           = inst["documentId"]
        eid           = inst["elementId"]
        partid        = inst.get("partId", "")
        configuration = inst["configuration"]
        client = get_client()
        ok = True
        try:
            # Exact same kwarg order as robot_builder.py:
            # **instance_request_params() → {wmvid, wmv, did, eid, linked_document_id, configuration}
            # + partid=...
            client.part_studio_stl_m(
                wmvid=wmvid, wmv=wmv, did=did, eid=eid,
                linked_document_id=document_id, configuration=configuration,
                partid=partid,
            )
        except Exception:
            ok = False
        try:
            client.part_get_metadata(
                wmvid=wmvid, wmv=wmv, did=did, eid=eid,
                linked_document_id=document_id, configuration=configuration,
                partid=partid,
            )
        except Exception:
            ok = False
        with lock:
            done_count[0] += 1
            if not ok:
                fail_count[0] += 1
            n = done_count[0]
            if n % 20 == 0 or n == total:
                f = fail_count[0]
                print(f"[PREWARM] {n}/{total} cached ({f} errors)", flush=True)
        return ok

    # Skip pre-warm for small assemblies — direct download is fast enough
    PREWARM_THRESHOLD = 10
    if total <= PREWARM_THRESHOLD:
        print(f"[PREWARM] {total} parts — skipping pre-warm (≤{PREWARM_THRESHOLD}), downloading directly", flush=True)
        return

    with ThreadPoolExecutor(max_workers=10, initializer=get_client) as executor:
        list(executor.map(warm_part, unique_parts))

    cached = done_count[0] - fail_count[0]
    print(f"[PREWARM] Done — {cached}/{total} parts cached successfully", flush=True)


def export_urdf_cli(onshape_url, assembly_name, output_dir='output', config_file=None,
                    access_key=None, secret_key=None, credentials_file=None):
    """
    Export URDF using onshape-to-robot command-line tool

    Note: onshape-to-robot expects a directory path as the first argument,
    and looks for config.json in that directory.
    """
    # Get API credentials
    try:
        access_key, secret_key = get_api_credentials(access_key, secret_key, credentials_file)
        print("API credentials loaded successfully")
    except ValueError as e:
        print(f"Warning: {e}")
        print("Attempting to continue without explicit credentials...")

    # Parse URL to get documentId
    document_id, workspace_id, element_id = parse_onshape_url(onshape_url)

    # Create output directory — always use absolute path to avoid cwd confusion
    output_path = Path(output_dir).resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {output_path}")

    # Create or update config.json in output directory
    output_config_file = output_path / 'config.json'

    # Load base config if provided
    config_data = {}
    if config_file and Path(config_file).exists():
        with open(config_file, 'r') as f:
            config_data = json.load(f)

    # Update with URL-derived information
    config_data['documentId'] = document_id
    config_data['assemblyName'] = assembly_name
    if 'outputFormat' not in config_data:
        config_data['outputFormat'] = 'urdf'
    # noDynamics: only force-disable if user hasn't specified it.
    # We default to False so mass data is written to the URDF (enables mass panel).
    # If parts crash due to missing mass, the retry logic below auto-enables it.
    # Cache API responses so retries reuse already-fetched data (resume-style)
    if 'cache' not in config_data:
        config_data['cache'] = True

    # Write config.json to output directory
    with open(output_config_file, 'w') as f:
        json.dump(config_data, f, indent=2)
    print(f"Created config.json in output directory")

    # Pre-warm the file cache in parallel before running the serial CLI tool.
    # This downloads all part STLs and metadata concurrently (10 workers),
    # so the subsequent onshape-to-robot run reads everything from disk cache.
    print("\nPre-warming part cache in parallel...", flush=True)
    try:
        _prewarm_cache(output_config_file, document_id, assembly_name, access_key, secret_key)
    except Exception as e:
        print(f"[PREWARM] Pre-warm failed ({e}), continuing without cache...", flush=True)

    # Build command - onshape-to-robot expects directory path as first argument
    cmd = ['onshape-to-robot', str(output_path)]

    # Prepare environment variables
    env = os.environ.copy()
    if access_key:
        env['ONSHAPE_ACCESS_KEY'] = access_key
    if secret_key:
        env['ONSHAPE_SECRET_KEY'] = secret_key
    env['ONSHAPE_API'] = 'https://cad.onshape.com'

    print(f"\nRunning command: {' '.join(cmd)}")
    print("Starting URDF export...")

    _TIMEOUT_SIGNALS = (
        'ConnectTimeoutError', 'Connection timed out',
        'TimeoutError', 'Max retries exceeded',
        'ConnectTimeout',
    )
    _RATE_LIMIT_SIGNALS = (
        'API limit exceeded', 'ERROR (402)', 'ERROR (429)',
        '"status" : 402', '"status" : 429',
    )
    _AUTH_ERROR_SIGNALS = (
        'ERROR (403)', '"status" : 403',
        'ERROR (401)', '"status" : 401',
        'do not have permission', 'Resource does not exist',
    )
    MAX_RETRIES   = 3
    RETRY_DELAYS  = [15, 45, 90]   # seconds before each retry

    import re as _re

    last_exc      = None
    captured_out  = []   # accumulate output for timeout detection on failure

    for attempt in range(MAX_RETRIES):
        captured_out.clear()
        part_count  = 0
        total_parts = 0

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )

            for raw_line in proc.stdout:
                line = raw_line.rstrip()
                captured_out.append(line)

                # Parse total parts from "Found X root nodes"
                m_total = _re.search(r'Found (\d+) root nodes', line)
                if m_total:
                    total_parts = int(m_total.group(1))

                # Count each part being added and emit inline progress
                if line.startswith('+ Adding part '):
                    part_count += 1
                    if total_parts:
                        print(f"[PARTS] {part_count}/{total_parts} — {line[14:]}", flush=True)
                    else:
                        print(f"[PARTS] {part_count}/? — {line[14:]}", flush=True)
                else:
                    print(line, flush=True)

            proc.wait()

            combined = '\n'.join(captured_out)
            is_rate_limit = any(sig in combined for sig in _RATE_LIMIT_SIGNALS)

            is_auth_error = any(sig in combined for sig in _AUTH_ERROR_SIGNALS)

            if is_rate_limit:
                print(f"\n✗ Onshape API limit exceeded — please wait before retrying or upgrade your plan.", flush=True)
                raise subprocess.CalledProcessError(402, cmd, output=combined)

            if is_auth_error:
                print(f"\n✗ Onshape API access denied (403) — the API credentials do not have permission to access this document. Share the document with your API account in Onshape.", flush=True)
                raise subprocess.CalledProcessError(403, cmd, output=combined)

            if proc.returncode != 0:
                raise subprocess.CalledProcessError(
                    proc.returncode, cmd,
                    output=combined,
                )

            break   # ── Success ──

        except subprocess.CalledProcessError as e:
            last_exc = e
            out = e.output or '\n'.join(captured_out)
            is_timeout = any(sig in out for sig in _TIMEOUT_SIGNALS)
            is_rate_limit = any(sig in out for sig in _RATE_LIMIT_SIGNALS) or e.returncode == 402
            is_auth_error = any(sig in out for sig in _AUTH_ERROR_SIGNALS) or e.returncode == 403
            is_mass_error = any(sig in out for sig in ("KeyError: 'mass'", 'KeyError: "mass"', 'has no mass'))

            # Rate limit or auth error — no retry
            if is_rate_limit or is_auth_error:
                raise

            # Auto-retry with noDynamics if some parts lack mass data
            if is_mass_error and not config_data.get('noDynamics') and attempt < MAX_RETRIES - 1:
                print(f"\n⚠ Some parts have no mass — retrying with noDynamics enabled (mass panel will be hidden)…", flush=True)
                config_data['noDynamics'] = True
                with open(output_config_file, 'w') as f:
                    json.dump(config_data, f, indent=2)
                continue

            if is_timeout and attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[attempt]
                print(f"\n⚠ Network timeout on attempt {attempt + 1}/{MAX_RETRIES}.", flush=True)
                print(f"  Already-fetched parts are cached — retrying in {delay}s…", flush=True)
                time.sleep(delay)
                continue

            print(f"\n✗ Error during URDF export:", flush=True)
            print(f"  Return code: {e.returncode}", flush=True)
            raise

        except FileNotFoundError:
            raise FileNotFoundError(
                "onshape-to-robot command not found. "
                "Please install it using: pip install onshape-to-robot"
            )
    else:
        print(f"\n✗ Export failed after {MAX_RETRIES} attempts (network timeout).", flush=True)
        raise last_exc

    # ── Post-processing (only reached on success) ──
    urdf_file = output_path / 'robot.urdf'
    if urdf_file.exists():
        print("\nFixing mesh file paths in URDF...")
        fix_urdf_mesh_paths(urdf_file, output_path)

    print("\nCleaning up unnecessary files...")
    cleanup_export_directory(output_path)

    print(f"\n✓ URDF export completed successfully!")
    print(f"  Output files saved to: {output_path.absolute()}")
    print(f"  - URDF: robot.urdf")


def export_urdf_python(onshape_url, assembly_name, output_dir='output', config_file=None, 
                       access_key=None, secret_key=None, credentials_file=None):
    """
    Export URDF using onshape-to-robot Python API
    Note: This function is not currently implemented as onshape-to-robot
    is primarily designed as a command-line tool. Falling back to CLI.
    """
    print("Note: Python API not fully supported, using command-line tool instead.")
    export_urdf_cli(onshape_url, assembly_name, output_dir, config_file)


def export_urdf(onshape_url, assembly_name, output_dir='output', config_file=None, use_cli=None,
                access_key=None, secret_key=None, credentials_file=None):
    """
    Export URDF from Onshape assembly
    
    Args:
        onshape_url: Full Onshape URL to the document
        assembly_name: Name of the assembly tab (e.g., "URDF_Top_Assembly")
        output_dir: Directory to save the exported URDF files
        config_file: Optional path to config.json file
        use_cli: Force use of CLI (True) or Python API (False), or auto-detect (None)
        access_key: Optional Onshape API access key
        secret_key: Optional Onshape API secret key
        credentials_file: Optional path to credentials file
    """
    # Auto-detect method if not specified
    if use_cli is None:
        use_cli = not HAS_PYTHON_API
    
    if use_cli:
        export_urdf_cli(onshape_url, assembly_name, output_dir, config_file,
                        access_key, secret_key, credentials_file)
    else:
        export_urdf_python(onshape_url, assembly_name, output_dir, config_file,
                          access_key, secret_key, credentials_file)


def main():
    parser = argparse.ArgumentParser(
        description='Export URDF from Onshape using onshape-to-robot'
    )
    parser.add_argument(
        '--url',
        type=str,
        default='https://cad.onshape.com/documents/7d0d24259dc99910b3744602/w/d63f2853da80ae1cf4ad7c0f/e/31489050b7b35d8fe159ddfa',
        help='Onshape document URL'
    )
    parser.add_argument(
        '--assembly',
        type=str,
        default='URDF_Top_Assembly',
        help='Assembly tab name (default: URDF_Top_Assembly)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='output',
        help='Output directory (default: output)'
    )
    parser.add_argument(
        '--config',
        type=str,
        default='config.json',
        help='Path to config.json file (default: config.json)'
    )
    parser.add_argument(
        '--use-cli',
        action='store_true',
        help='Force use of command-line tool instead of Python API'
    )
    parser.add_argument(
        '--use-python-api',
        action='store_true',
        help='Force use of Python API (currently falls back to CLI)'
    )
    parser.add_argument(
        '--access-key',
        type=str,
        help='Onshape API access key (optional, can also use env var or credentials file)'
    )
    parser.add_argument(
        '--secret-key',
        type=str,
        help='Onshape API secret key (optional, can also use env var or credentials file)'
    )
    parser.add_argument(
        '--credentials-file',
        type=str,
        help='Path to credentials file (JSON format with access_key and secret_key)'
    )
    
    args = parser.parse_args()
    
    # Determine which method to use
    use_cli = None
    if args.use_cli:
        use_cli = True
    elif args.use_python_api:
        use_cli = False
    
    try:
        export_urdf(
            onshape_url=args.url,
            assembly_name=args.assembly,
            output_dir=args.output,
            config_file=args.config,
            use_cli=use_cli,
            access_key=args.access_key,
            secret_key=args.secret_key,
            credentials_file=args.credentials_file
        )
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

