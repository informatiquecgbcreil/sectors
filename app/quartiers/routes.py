from __future__ import annotations

from collections import defaultdict

from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_required
from sqlalchemy import func

from app.extensions import db
from app.models import Quartier, Participant, PresenceActivite, SessionActivite, AtelierActivite
from app.rbac import require_perm
from app.statsimpact.engine import _session_date_expr

from . import bp


def _load_quartiers():
    return Quartier.query.order_by(Quartier.ville.asc(), Quartier.nom.asc()).all()


@bp.route("/")
@login_required
@require_perm("quartiers:view")
def index():
    quartiers = _load_quartiers()
    return render_template("quartiers/index.html", quartiers=quartiers)


@bp.route("/new", methods=["POST"])
@login_required
@require_perm("quartiers:edit")
def create():
    ville = (request.form.get("ville") or "").strip() or None
    nom = (request.form.get("nom") or "").strip() or None
    description = (request.form.get("description") or "").strip() or None
    is_qpv = request.form.get("is_qpv") == "1"

    if not ville or not nom:
        flash("Ville et nom sont obligatoires.", "danger")
        return redirect(url_for("quartiers.index"))

    existing = Quartier.query.filter_by(ville=ville, nom=nom).first()
    if existing:
        flash("Ce quartier existe déjà pour cette ville.", "warning")
        return redirect(url_for("quartiers.index"))

    db.session.add(Quartier(ville=ville, nom=nom, description=description, is_qpv=is_qpv))
    db.session.commit()
    flash("Quartier ajouté.", "success")
    return redirect(url_for("quartiers.index"))


@bp.route("/<int:quartier_id>/edit", methods=["GET", "POST"])
@login_required
@require_perm("quartiers:edit")
def edit(quartier_id: int):
    quartier = Quartier.query.get_or_404(quartier_id)
    if request.method == "POST":
        ville = (request.form.get("ville") or "").strip() or None
        nom = (request.form.get("nom") or "").strip() or None
        description = (request.form.get("description") or "").strip() or None
        is_qpv = request.form.get("is_qpv") == "1"

        if not ville or not nom:
            flash("Ville et nom sont obligatoires.", "danger")
            return redirect(url_for("quartiers.edit", quartier_id=quartier.id))

        existing = (
            Quartier.query.filter_by(ville=ville, nom=nom)
            .filter(Quartier.id != quartier.id)
            .first()
        )
        if existing:
            flash("Un quartier avec ce nom existe déjà pour cette ville.", "warning")
            return redirect(url_for("quartiers.edit", quartier_id=quartier.id))

        quartier.ville = ville
        quartier.nom = nom
        quartier.description = description
        quartier.is_qpv = is_qpv
        db.session.commit()
        flash("Quartier mis à jour.", "success")
        return redirect(url_for("quartiers.index"))

    return render_template("quartiers/edit.html", quartier=quartier)


@bp.route("/<int:quartier_id>/delete", methods=["POST"])
@login_required
@require_perm("quartiers:delete")
def delete(quartier_id: int):
    quartier = Quartier.query.get_or_404(quartier_id)
    linked = Participant.query.filter_by(quartier_id=quartier.id).first()
    if linked:
        flash("Suppression impossible : ce quartier est lié à des participants.", "warning")
        return redirect(url_for("quartiers.index"))

    db.session.delete(quartier)
    db.session.commit()
    flash("Quartier supprimé.", "success")
    return redirect(url_for("quartiers.index"))


@bp.route("/stats")
@login_required
@require_perm("quartiers:view")
def stats():
    quartiers = _load_quartiers()
    quartier_id = request.args.get("quartier_id")
    quartier = None

    stats_payload = None
    if quartier_id:
        try:
            quartier_id_int = int(quartier_id)
        except ValueError:
            quartier_id_int = None
        if quartier_id_int:
            quartier = Quartier.query.get(quartier_id_int)

    if quartier:
        participants = Participant.query.filter_by(quartier_id=quartier.id).all()
        participant_count = len(participants)
        ages = [p.age for p in participants if p.age is not None]
        avg_age = round(sum(ages) / len(ages), 1) if ages else None

        gender_counts = defaultdict(int)
        for p in participants:
            label = (p.genre or "").strip() or "Non renseigné"
            gender_counts[label] += 1

        presence_count = (
            db.session.query(func.count(PresenceActivite.id))
            .join(Participant, Participant.id == PresenceActivite.participant_id)
            .filter(Participant.quartier_id == quartier.id)
            .scalar()
            or 0
        )

        secteur_rows = (
            db.session.query(
                SessionActivite.secteur,
                func.count(func.distinct(Participant.id)).label("participants"),
                func.count(PresenceActivite.id).label("presences"),
            )
            .join(PresenceActivite, PresenceActivite.session_id == SessionActivite.id)
            .join(Participant, Participant.id == PresenceActivite.participant_id)
            .filter(Participant.quartier_id == quartier.id)
            .group_by(SessionActivite.secteur)
            .order_by(SessionActivite.secteur.asc())
            .all()
        )

        atelier_rows = (
            db.session.query(
                AtelierActivite.nom,
                func.count(func.distinct(Participant.id)).label("participants"),
                func.count(PresenceActivite.id).label("presences"),
            )
            .join(SessionActivite, SessionActivite.atelier_id == AtelierActivite.id)
            .join(PresenceActivite, PresenceActivite.session_id == SessionActivite.id)
            .join(Participant, Participant.id == PresenceActivite.participant_id)
            .filter(Participant.quartier_id == quartier.id)
            .group_by(AtelierActivite.nom)
            .order_by(func.count(PresenceActivite.id).desc())
            .all()
        )

        dialect = db.engine.dialect.name
        session_date = _session_date_expr()
        if dialect == "sqlite":
            month_expr = func.strftime("%Y-%m", session_date)
        else:
            month_expr = func.to_char(session_date, "YYYY-MM")

        month_rows = (
            db.session.query(
                month_expr.label("month"),
                func.count(PresenceActivite.id).label("presences"),
            )
            .join(PresenceActivite, PresenceActivite.session_id == SessionActivite.id)
            .join(Participant, Participant.id == PresenceActivite.participant_id)
            .filter(Participant.quartier_id == quartier.id)
            .filter(session_date.isnot(None))
            .group_by(month_expr)
            .order_by(month_expr.asc())
            .all()
        )

        stats_payload = {
            "participant_count": participant_count,
            "presence_count": int(presence_count),
            "avg_age": avg_age,
            "gender_counts": dict(sorted(gender_counts.items(), key=lambda x: x[0].lower())),
            "secteurs": secteur_rows,
            "ateliers": atelier_rows,
            "months": month_rows,
        }

    return render_template(
        "quartiers/stats.html",
        quartiers=quartiers,
        quartier=quartier,
        stats=stats_payload,
    )
