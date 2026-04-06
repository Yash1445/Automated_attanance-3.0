from flask_sqlalchemy import SQLAlchemy
import os
from urllib.parse import quote_plus

# Create database object
db = SQLAlchemy()

def init_db_config(app):
    # Prefer DATABASE_URL or DB_* PostgreSQL settings.
    database_url = os.getenv("DATABASE_URL", "").strip()

    if database_url:
        app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    else:
        db_user = os.getenv("DB_USER", "postgres")
        db_password = quote_plus(os.getenv("DB_PASSWORD", ""))
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = os.getenv("DB_PORT", "5432")
        db_name = os.getenv("DB_NAME", "attendance_system_db")

        if db_password:
            app.config["SQLALCHEMY_DATABASE_URI"] = (
                f"postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
            )
        else:
            app.config["SQLALCHEMY_DATABASE_URI"] = (
                f"postgresql+psycopg2://{db_user}@{db_host}:{db_port}/{db_name}"
            )
    
    # Disable modification tracking (recommended)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Initialize DB with Flask app
    db.init_app(app)