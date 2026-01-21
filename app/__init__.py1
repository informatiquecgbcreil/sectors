import os
from flask import Flask
from sqlalchemy import text
from config import Config
from app.extensions import db, login_manager, csrf
from app.models import User

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from app.auth.routes import bp as auth_bp
    from app.main.routes import bp as main_bp
    from app.budget.routes import bp as budget_bp
    from app.projets.routes import bp as projets_bp
    from app.admin.routes import bp as admin_bp
    from app.activite import bp as activite_bp
    from app.kiosk import bp as kiosk_bp
    from app.statsimpact.routes import bp as statsimpact_bp
    from app.inventaire.routes import bp as inventaire_bp
    from app.inventaire_materiel.routes import bp as inventaire_materiel_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(budget_bp)
    app.register_blueprint(projets_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(activite_bp)
    app.register_blueprint(kiosk_bp)
    app.register_blueprint(statsimpact_bp)
    app.register_blueprint(inventaire_bp)
    app.register_blueprint(inventaire_materiel_bp)


    def ensure_schema():
        """Migration légère (SQLite) : ajoute les colonnes manquantes sans Alembic."""
        # 1) Finance : colonne nature sur ligne_budget
        try:
            cols = [row[1] for row in db.session.execute(text("PRAGMA table_info(ligne_budget)")).all()]
            if "nature" not in cols:
                db.session.execute(text(
                    "ALTER TABLE ligne_budget ADD COLUMN nature VARCHAR(10) NOT NULL DEFAULT 'charge'"
                ))
                # Heuristique: les comptes 7* sont des produits
                db.session.execute(text(
                    "UPDATE ligne_budget SET nature='produit' WHERE compte LIKE '7%'"
                ))
                db.session.commit()
        except Exception:
            # si la table n'existe pas encore, create_all la créera
            db.session.rollback()

        # 2) Activité : colonnes kiosque sur session_activite
        try:
            cols_s = [row[1] for row in db.session.execute(text("PRAGMA table_info(session_activite)")).all()]
            alters = []
            if 'is_deleted' not in cols_s:
                alters.append("ALTER TABLE session_activite ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0")
            if 'deleted_at' not in cols_s:
                alters.append("ALTER TABLE session_activite ADD COLUMN deleted_at DATETIME")
            if 'kiosk_open' not in cols_s:
                alters.append("ALTER TABLE session_activite ADD COLUMN kiosk_open BOOLEAN NOT NULL DEFAULT 0")
            if 'kiosk_pin' not in cols_s:
                alters.append("ALTER TABLE session_activite ADD COLUMN kiosk_pin VARCHAR(10)")
            if 'kiosk_token' not in cols_s:
                alters.append("ALTER TABLE session_activite ADD COLUMN kiosk_token VARCHAR(64)")
            if 'kiosk_opened_at' not in cols_s:
                alters.append("ALTER TABLE session_activite ADD COLUMN kiosk_opened_at DATETIME")
            for sql in alters:
                db.session.execute(text(sql))
            if alters:
                db.session.commit()
        except Exception:
            db.session.rollback()

        # 3) Activité : soft-delete sur atelier_activite
        try:
            cols_a = [row[1] for row in db.session.execute(text("PRAGMA table_info(atelier_activite)")).all()]
            alters = []
            if 'is_deleted' not in cols_a:
                alters.append("ALTER TABLE atelier_activite ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0")
            if 'deleted_at' not in cols_a:
                alters.append("ALTER TABLE atelier_activite ADD COLUMN deleted_at DATETIME")
            for sql in alters:
                db.session.execute(text(sql))
            if alters:
                db.session.commit()
        except Exception:
            db.session.rollback()

        # 4) Activité : type_public sur participant
        try:
            cols_p = [row[1] for row in db.session.execute(text("PRAGMA table_info(participant)")).all()]
            if "type_public" not in cols_p:
                db.session.execute(text("ALTER TABLE participant ADD COLUMN type_public VARCHAR(2) NOT NULL DEFAULT 'H'"))
                db.session.commit()
        except Exception:
            db.session.rollback()

        # 5) Activité : archives (version corrigée + suivi mail)
        try:
            cols_ar = [row[1] for row in db.session.execute(text("PRAGMA table_info(archive_emargement)")).all()]
            alters = []
            if "corrected_docx_path" not in cols_ar:
                alters.append("ALTER TABLE archive_emargement ADD COLUMN corrected_docx_path VARCHAR(255)")
            if "corrected_pdf_path" not in cols_ar:
                alters.append("ALTER TABLE archive_emargement ADD COLUMN corrected_pdf_path VARCHAR(255)")
            if "last_emailed_to" not in cols_ar:
                alters.append("ALTER TABLE archive_emargement ADD COLUMN last_emailed_to VARCHAR(255)")
            if "last_emailed_at" not in cols_ar:
                alters.append("ALTER TABLE archive_emargement ADD COLUMN last_emailed_at DATETIME")
            for sql in alters:
                db.session.execute(text(sql))
            if alters:
                db.session.commit()
        except Exception:
            db.session.rollback()

        # 6) Index unique anti-doublons (collectif)
        try:
            db.session.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_uq_presence_session_participant ON presence_activite(session_id, participant_id)"
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()

        # 7) Finance : dépense liée à une ligne de facture (inventaire)
        try:
            cols_dep = [row[1] for row in db.session.execute(text("PRAGMA table_info(depense)")).all()]
            if "facture_ligne_id" not in cols_dep:
                db.session.execute(text(
                    "ALTER TABLE depense ADD COLUMN facture_ligne_id INTEGER REFERENCES facture_ligne(id)"
                ))
                db.session.commit()
        except Exception:
            db.session.rollback()
    with app.app_context():
        ensure_schema()
        db.create_all()

    return app
