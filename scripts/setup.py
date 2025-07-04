#!/usr/bin/env python3
"""Setup script for the loan market simulation."""

import subprocess
import sys

def install_requirements():
    """Install required packages."""
    print("Installing required packages...")
    
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        ])
        print("✓ All packages installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install packages: {e}")
        return False

def main():
    """Main setup function."""
    print("=" * 50)
    print("LOAN MARKET SIMULATION - SETUP")
    print("=" * 50)
    
    if install_requirements():
        print("\n✅ Setup complete!")
        print("\nNext steps:")
        print("1. Set up your OpenAI API key: export OPENAI_API_KEY='your-key-here'")
        print("2. Run verification: python3 verify_implementation.py")
        print("3. Run simulation: python3 run_sim.py --test-mode")
        return 0
    else:
        print("\n❌ Setup failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())