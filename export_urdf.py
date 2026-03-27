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
    # Prevent crash when parts have no material/mass assigned in Onshape
    if 'noDynamics' not in config_data:
        config_data['noDynamics'] = True
    # Cache API responses so retries reuse already-fetched data (resume-style)
    if 'cache' not in config_data:
        config_data['cache'] = True
    
    # Write config.json to output directory
    with open(output_config_file, 'w') as f:
        json.dump(config_data, f, indent=2)
    print(f"Created config.json in output directory")
    
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

            if proc.returncode != 0:
                raise subprocess.CalledProcessError(
                    proc.returncode, cmd,
                    output='\n'.join(captured_out),
                )

            break   # ── Success ──

        except subprocess.CalledProcessError as e:
            last_exc = e
            combined = '\n'.join(captured_out)
            is_timeout = any(sig in combined for sig in _TIMEOUT_SIGNALS)

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

