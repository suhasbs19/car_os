"""
CAR OS - Main Application Entry Point
Intelligent Vehicle System and Cost Management Platform
"""
import os
from flask import Flask
from config import config_map
from models import db


def create_app(config_name: str = "default") -> Flask:
    """Application factory pattern."""
    app = Flask(__name__, instance_relative_config=True)

    # Load config
    app.config.from_object(config_map[config_name])

    # Ensure instance folder exists
    os.makedirs(app.instance_path, exist_ok=True)

    # Initialize extensions
    db.init_app(app)

    # Register blueprints
    from routes.vehicle_routes import vehicle_bp
    from routes.maintenance_routes import maintenance_bp
    from routes.fuel_routes import fuel_bp
    from routes.analytics_routes import analytics_bp

    app.register_blueprint(vehicle_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(fuel_bp)
    app.register_blueprint(analytics_bp)

    # Create tables & apply non-destructive SQLite migrations
    with app.app_context():
        from models.vehicle_models import apply_sqlite_migrations
        apply_sqlite_migrations(db.engine)
        db.create_all()

    # Template filters
    @app.template_filter("inr")
    def format_inr_filter(value):
        if value is None:
            return "N/A"
        try:
            v = float(value)
            if v >= 1_00_000:
                return f"₹{v/1_00_000:.2f}L"
            elif v >= 1_000:
                return f"₹{v:,.0f}"
            return f"₹{v:,.0f}"
        except (TypeError, ValueError):
            return "N/A"

    @app.template_filter("lakh")
    def lakh_filter(value):
        if value is None:
            return "N/A"
        try:
            v = float(value)
            if v >= 1_00_000:
                return f"₹{v/1_00_000:.2f} Lakh"
            return f"₹{v:,.0f}"
        except (TypeError, ValueError):
            return "N/A"

    @app.template_filter("round2")
    def round2_filter(value):
        if value is None:
            return "N/A"
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return "N/A"

    return app


if __name__ == "__main__":
    app = create_app("development")
    app.run(debug=True, host="127.0.0.1", port=5000)
