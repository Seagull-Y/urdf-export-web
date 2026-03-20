#!/usr/bin/env python3
"""
Script to verify URDF file in MuJoCo
"""

import os
import sys
import argparse
from pathlib import Path

try:
    import mujoco
    import mujoco.viewer
    HAS_MUJOCO = True
except ImportError:
    HAS_MUJOCO = False
    print("Warning: MuJoCo is not installed. Installing...")
    print("Please run: pip install mujoco")


def fix_urdf_paths(urdf_path):
    """
    Fix package:// paths in URDF to absolute paths for MuJoCo
    """
    import xml.etree.ElementTree as ET
    import tempfile
    import shutil
    
    urdf_path = Path(urdf_path)
    urdf_dir = urdf_path.parent
    
    # Parse URDF
    tree = ET.parse(urdf_path)
    root = tree.getroot()
    
    # Remove namespace for easier processing
    for elem in root.iter():
        if '}' in elem.tag:
            elem.tag = elem.tag.split('}')[1]
    
    # Find all mesh elements
    mesh_count = 0
    for mesh in root.iter('mesh'):
        if 'filename' in mesh.attrib:
            filename = mesh.attrib['filename']
            # Replace package:// with absolute path
            if filename.startswith('package://'):
                # Remove package:// prefix
                rel_path = filename.replace('package://', '')
                # Make it absolute path relative to URDF directory
                abs_path = (urdf_dir / rel_path).resolve()
                if abs_path.exists():
                    mesh.attrib['filename'] = str(abs_path)
                    mesh_count += 1
                    if mesh_count <= 3:  # Print first few
                        print(f"  Fixed path: {filename} -> {abs_path}")
                else:
                    print(f"  Warning: File not found: {abs_path}")
    
    # Write to temporary file in the same directory as URDF
    temp_file = tempfile.NamedTemporaryFile(
        mode='w', 
        suffix='.urdf', 
        delete=False,
        dir=str(urdf_dir)
    )
    # Write with proper formatting
    ET.indent(tree, space='  ')
    tree.write(temp_file.name, encoding='utf-8', xml_declaration=True)
    temp_file.close()
    
    return temp_file.name


def verify_urdf(urdf_path, visualize=True):
    """
    Verify URDF file by loading it in MuJoCo
    
    Args:
        urdf_path: Path to URDF file
        visualize: Whether to open interactive viewer
    """
    urdf_path = Path(urdf_path)
    
    if not urdf_path.exists():
        raise FileNotFoundError(f"URDF file not found: {urdf_path}")
    
    print(f"Loading URDF file: {urdf_path.absolute()}")
    
    try:
        # Fix package:// paths for MuJoCo using string replacement (more reliable)
        print("Fixing mesh paths for MuJoCo...")
        urdf_dir = urdf_path.parent
        
        with open(urdf_path, 'r') as f:
            urdf_content = f.read()
        
        # MuJoCo has issues with subdirectories in mesh paths - it only reads the filename
        # Solution: Copy STL files to the same directory as URDF or use symlinks
        import re
        import shutil
        
        # Extract all STL file references (handle both package://assets/ and assets/ formats)
        stl_files_package = set(re.findall(r'package://assets/([^\"]+\.stl)', urdf_content))
        stl_files_relative = set(re.findall(r'filename=\"assets/([^\"]+\.stl)\"', urdf_content))
        stl_files = stl_files_package | stl_files_relative
        print(f"  Found {len(stl_files)} unique STL files")
        
        # Copy STL files to output directory (or create symlinks)
        assets_dir = urdf_dir / 'assets'
        copied_files = []
        for stl_file in stl_files:
            src = assets_dir / stl_file
            dst = urdf_dir / stl_file
            if src.exists():
                if not dst.exists():
                    shutil.copy2(src, dst)
                    copied_files.append(stl_file)
                    print(f"    Copied {stl_file} to output directory")
            else:
                print(f"    Warning: {src} not found")
        
        # Replace paths with just the filename (since files are now in same dir)
        # Handle both package://assets/ and assets/ formats
        def replace_path(match):
            rel_path = match.group(1) if match.lastindex >= 1 else match.group(0)
            # Extract just the filename
            filename = Path(rel_path).name
            return f'filename=\"{filename}\"'
        
        # Replace package://assets/ paths
        urdf_content_fixed = re.sub(
            r'filename=\"package://assets/([^\"]+)\"',
            replace_path,
            urdf_content
        )
        # Replace assets/ paths
        urdf_content_fixed = re.sub(
            r'filename=\"assets/([^\"]+\.stl)\"',
            replace_path,
            urdf_content_fixed
        )
        
        # Count replacements
        original_count = len(re.findall(r'package://', urdf_content))
        remaining_count = len(re.findall(r'package://', urdf_content_fixed))
        if original_count > 0:
            print(f"  Fixed {original_count} package:// paths to filenames")
            if remaining_count > 0:
                print(f"  Warning: {remaining_count} package:// paths still remain")
        
        # Write to a fixed URDF file in the output directory
        fixed_urdf_path = urdf_dir / 'robot_fixed.urdf'
        with open(fixed_urdf_path, 'w') as f:
            f.write(urdf_content_fixed)
        print(f"  Created fixed URDF: {fixed_urdf_path}")
        
        # Change to output directory and load (STL files are now in same directory)
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(str(urdf_dir))
            model = mujoco.MjModel.from_xml_path('robot_fixed.urdf')
            data = mujoco.MjData(model)
        finally:
            os.chdir(old_cwd)
        
        print("\n✓ URDF loaded successfully in MuJoCo!")
        print(f"\nModel Information:")
        print(f"  - Number of bodies: {model.nbody}")
        print(f"  - Number of joints: {model.njnt}")
        print(f"  - Number of degrees of freedom: {model.nv}")
        print(f"  - Number of actuators: {model.nu}")
        print(f"  - Number of sensors: {model.nsensor}")
        print(f"  - Number of constraints: {model.nconmax}")
        
        # Print joint information
        if model.njnt > 0:
            print(f"\nJoints:")
            for i in range(model.njnt):
                joint_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i)
                joint_type = model.jnt_type[i]
                type_names = {
                    0: "free",
                    1: "ball",
                    2: "slide",
                    3: "hinge"
                }
                type_name = type_names.get(joint_type, f"unknown({joint_type})")
                print(f"  - {joint_name}: {type_name}")
        
        # Print body information
        if model.nbody > 0:
            print(f"\nBodies (first 10):")
            for i in range(min(10, model.nbody)):
                body_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i)
                if body_name:
                    print(f"  - {body_name}")
            if model.nbody > 10:
                print(f"  ... and {model.nbody - 10} more bodies")
        
        # Forward kinematics
        mujoco.mj_forward(model, data)
        print(f"\n✓ Forward kinematics computed successfully")
        
        # Check for warnings (data.warning.number is an array)
        try:
            warning_count = data.warning.number[0] if hasattr(data.warning.number, '__getitem__') else data.warning.number
            if warning_count > 0:
                print(f"\n⚠ Warnings detected: {warning_count}")
                for i in range(warning_count):
                    print(f"  - {mujoco.mj_warningText(data.warning.lastinfo[i])}")
        except (IndexError, TypeError):
            # Skip warning check if there's an issue
            pass
        
        # Visualize if requested
        if visualize:
            print(f"\nOpening MuJoCo viewer...")
            print("Press ESC or close the window to exit")
            try:
                import platform
                
                # On macOS, launch_passive requires mjpython, so use launch instead
                if platform.system() == 'Darwin':
                    print("Using interactive viewer for macOS...")
                    # Reset to initial position
                    mujoco.mj_resetData(model, data)
                    # Launch interactive viewer (blocks until window is closed)
                    mujoco.viewer.launch(model, data)
                else:
                    # On other platforms, use passive viewer
                    with mujoco.viewer.launch_passive(model, data) as viewer:
                        # Reset to initial position
                        mujoco.mj_resetData(model, data)
                        
                        # Run simulation loop
                        while viewer.is_running():
                            step_start = data.time
                            
                            # Step simulation
                            mujoco.mj_step(model, data)
                            
                            # Sync viewer
                            viewer.sync()
                            
                            # Small delay to control simulation speed
                            time_until_next_step = model.opt.timestep - (data.time - step_start)
                            if time_until_next_step > 0:
                                import time
                                time.sleep(min(time_until_next_step, 0.01))
            except KeyboardInterrupt:
                print("\nViewer closed by user")
            except Exception as e:
                print(f"\nError opening viewer: {e}")
                print("You can still verify the URDF was loaded successfully (see information above)")
                import traceback
                traceback.print_exc()
        
        return True
        
    except Exception as e:
        print(f"\n✗ Error loading URDF in MuJoCo:")
        print(f"  {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Verify URDF file in MuJoCo'
    )
    parser.add_argument(
        '--urdf',
        type=str,
        default='output/robot.urdf',
        help='Path to URDF file (default: output/robot.urdf)'
    )
    parser.add_argument(
        '--no-visualize',
        action='store_true',
        help='Skip visualization (only verify loading)'
    )
    
    args = parser.parse_args()
    
    if not HAS_MUJOCO:
        print("\nError: MuJoCo is not installed.")
        print("Please install it using: pip install mujoco")
        sys.exit(1)
    
    success = verify_urdf(args.urdf, visualize=not args.no_visualize)
    
    if success:
        print("\n✓ URDF verification completed successfully!")
        sys.exit(0)
    else:
        print("\n✗ URDF verification failed!")
        sys.exit(1)


if __name__ == '__main__':
    main()

