"""
CAR OS - Application Launcher
Launches the CAR OS Web Application on http://127.0.0.1:5000
"""
import sys
import os

# Ensure current directory is on python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

app = create_app(os.environ.get("FLASK_ENV", "development"))

if __name__ == "__main__":
    print("=" * 65)
    print("  CAR OS: Intelligent Vehicle System and Cost Management Platform")
    print("  Server starting on: http://127.0.0.1:5000")
    print("  Press Ctrl+C to stop the server.")
    print("=" * 65)
    app.run(host="127.0.0.1", port=5000, debug=True)
