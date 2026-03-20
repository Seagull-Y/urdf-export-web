#!/usr/bin/env python3
"""
Simple MuJoCo viewer for manually loading URDF files
"""

import sys
import os
import argparse
from pathlib import Path

# Ensure we're in the script's directory for relative paths
script_dir = Path(__file__).parent.absolute()
os.chdir(script_dir)

try:
    import mujoco
    import mujoco.viewer
except ImportError as e:
    print("Error: MuJoCo is not installed or not accessible.")
    print(f"Import error: {e}")
    print()
    print("Please install it using:")
    print("  pip install mujoco")
    print()
    print("Or if using a virtual environment:")
    print("  source .venv/bin/activate  # if you have .venv")
    print("  pip install mujoco")
    print()
    print("Current Python: " + sys.executable)
    sys.exit(1)


def view_urdf(urdf_path=None):
    """
    Open MuJoCo viewer for manual URDF loading
    """
    if urdf_path:
        urdf_path = Path(urdf_path)
        # If relative path, make it relative to script directory
        if not urdf_path.is_absolute():
            urdf_path = script_dir / urdf_path
        
        if not urdf_path.exists():
            print(f"Error: URDF file not found: {urdf_path}")
            print(f"Current working directory: {os.getcwd()}")
            print(f"Script directory: {script_dir}")
            sys.exit(1)
        
        print(f"Loading URDF: {urdf_path}")
        
        # Fix paths for MuJoCo (copy STL files to same directory)
        import re
        import shutil
        import os
        
        urdf_dir = urdf_path.parent
        with open(urdf_path, 'r') as f:
            content = f.read()
        
        # Copy STL files (handle both package://assets/ and assets/ formats)
        stl_files_package = set(re.findall(r'package://assets/([^\"]+\.stl)', content))
        stl_files_relative = set(re.findall(r'filename=\"assets/([^\"]+\.stl)\"', content))
        stl_files = stl_files_package | stl_files_relative
        
        assets_dir = urdf_dir / 'assets'
        for stl_file in stl_files:
            src = assets_dir / stl_file
            dst = urdf_dir / stl_file
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)
                print(f"  Copied {stl_file} to output directory")
        
        # Fix paths - handle both formats
        # Replace package://assets/ paths
        content_fixed = re.sub(r'filename=\"package://assets/([^\"]+)\"', 
                               lambda m: f'filename=\"{Path(m.group(1)).name}\"', 
                               content)
        # Replace assets/ paths
        content_fixed = re.sub(r'filename=\"assets/([^\"]+\.stl)\"',
                               lambda m: f'filename=\"{Path(m.group(1)).name}\"',
                               content_fixed)
        
        fixed_urdf = urdf_dir / 'temp_viewer.urdf'
        with open(fixed_urdf, 'w') as f:
            f.write(content_fixed)
        
        # Change to URDF directory and load
        old_cwd = os.getcwd()
        try:
            os.chdir(str(urdf_dir))
            model = mujoco.MjModel.from_xml_path('temp_viewer.urdf')
            data = mujoco.MjData(model)
            mujoco.mj_resetData(model, data)
            
            print(f"\n✓ URDF loaded successfully!")
            print(f"  Bodies: {model.nbody}")
            print(f"  Joints: {model.njnt}")
            print(f"  DOF: {model.nv}")
            print(f"\nOpening MuJoCo viewer...")
            print("Press ESC or close the window to exit")
            
            mujoco.viewer.launch(model, data)
        finally:
            os.chdir(old_cwd)
            if fixed_urdf.exists():
                fixed_urdf.unlink()
    else:
        # Open empty viewer for manual file selection
        print("Opening MuJoCo viewer...")
        print("You can manually load URDF files from the viewer interface")
        print("Or specify a URDF file with: python3 mujoco_viewer.py --urdf <path>")
        
        # Create a minimal model for the viewer
        xml = '''<?xml version="1.0"?>
<mujoco model="empty">
  <worldbody>
    <light pos="0 0 3"/>
    <geom type="plane" size="1 1 0.1" rgba="0.8 0.8 0.8 1"/>
  </worldbody>
</mujoco>'''
        
        model = mujoco.MjModel.from_xml_string(xml.encode())
        data = mujoco.MjData(model)
        mujoco.viewer.launch(model, data)


def main():
    parser = argparse.ArgumentParser(
        description='MuJoCo viewer for URDF files'
    )
    parser.add_argument(
        '--urdf',
        type=str,
        default='output/robot.urdf',
        help='Path to URDF file to load (default: output/robot.urdf)'
    )
    
    args = parser.parse_args()
    
    try:
        # Check if default URDF exists, if not, open empty viewer
        urdf_path = script_dir / args.urdf if not Path(args.urdf).is_absolute() else Path(args.urdf)
        if not urdf_path.exists() and args.urdf == 'output/robot.urdf':
            print(f"Default URDF not found: {urdf_path}")
            print("Opening empty viewer for manual file selection...")
            print("You can drag and drop URDF files into the viewer window")
            view_urdf(None)
        else:
            view_urdf(str(urdf_path))
    except KeyboardInterrupt:
        print("\nViewer closed by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

