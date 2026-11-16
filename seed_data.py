"""
CAR OS - Database Seeder
========================
Populates the database with realistic demonstration vehicles,
maintenance logs, fuel/energy logs, diagnostics, and expense records
by delegating to the safe reset_demo_data engine without dropping tables.
"""
import sys
import os

# Ensure project root is on Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from scripts.reset_demo_data import execute_reset_and_seeding


def seed_database(apply_changes: bool = True):
    app = create_app("development")
    return execute_reset_and_seeding(app, apply_changes=apply_changes)


if __name__ == "__main__":
    seed_database(apply_changes=True)
