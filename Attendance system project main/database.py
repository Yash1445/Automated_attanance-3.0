from flask_sqlalchemy import SQLAlchemy

# Create database object
db = SQLAlchemy()

def init_db_config(app):
    # Use SQLite (works on Render without setup)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///attendance.db"
    
    # Disable modification tracking (recommended)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Initialize DB with Flask app
    db.init_app(app)