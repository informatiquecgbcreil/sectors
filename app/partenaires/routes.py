from __future__ import annotations

from datetime import date

from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Partenaire, PartenaireSecteur, PartenaireIntervention
from app.rbac import require_perm

from . import bp


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except Exception:
        return None


def _selected_secteurs_from_request() -> list[str]:
    secteurs = request.values.getlist("secteur")
    cleaned = [s.strip() for s in secteurs if s and s.strip()]
    return list(dict.fromkeys(cleaned))


@bp.route("/")
@login_required
@require_perm("partenaires:view")
def index():
    q = (request.args.get("q") or "").strip()
    secteurs = _selected_secteurs_from_request()

    base = Partenaire.query
    if q:
        like = f"%{q.lower()}%"
        base = base.filter(
            db.or_(
                db.func.lower(Partenaire.nom).like(like),
                db.func.lower(db.func.coalesce(Partenaire.contact_nom, "")).like(like),
                db.func.lower(db.func.coalesce(Partenaire.contact_prenom, "")).like(like),
                db.func.lower(db.func.coalesce(Partenaire.email_contact, "")).like(like),
                db.func.lower(db.func.coalesce(Partenaire.email_general, "")).like(like),
                db.func.lower(db.func.coalesce(Partenaire.tel_contact, "")).like(like),
                db.func.lower(db.func.coalesce(Partenaire.tel_general, "")).like(like),
            )
        )

    if secteurs:
        base = (
            base.join(PartenaireSecteur)
            .filter(PartenaireSecteur.secteur.in_(secteurs))
        )

    partenaires = base.order_by(Partenaire.nom.asc()).distinct().all()
    return render_template(
        "partenaires/index.html",
        partenaires=partenaires,
        q=q,
        secteurs=secteurs,
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
@require_perm("partenaires:edit")
def create():
    if request.method == "POST":
        nom = (request.form.get("nom") or "").strip()
        if not nom:
            flash("Le nom du partenaire est obligatoire.", "danger")
            return redirect(url_for("partenaires.create"))

        partenaire = Partenaire(
            nom=nom,
            contact_nom=(request.form.get("contact_nom") or "").strip() or None,
            contact_prenom=(request.form.get("contact_prenom") or "").strip() or None,
            adresse=(request.form.get("adresse") or "").strip() or None,
            email_contact=(request.form.get("email_contact") or "").strip() or None,
            email_general=(request.form.get("email_general") or "").strip() or None,
            tel_contact=(request.form.get("tel_contact") or "").strip() or None,
            tel_general=(request.form.get("tel_general") or "").strip() or None,
            description=(request.form.get("description") or "").strip() or None,
        )
        db.session.add(partenaire)
        db.session.flush()

        secteurs = _selected_secteurs_from_request()
        for secteur in secteurs:
            db.session.add(PartenaireSecteur(partenaire_id=partenaire.id, secteur=secteur))

        db.session.commit()
        flash("Partenaire créé.", "success")
        return redirect(url_for("partenaires.edit", partenaire_id=partenaire.id))

    return render_template("partenaires/form.html", partenaire=None, secteurs=[])


@bp.route("/<int:partenaire_id>/edit", methods=["GET", "POST"])
@login_required
@require_perm("partenaires:edit")
def edit(partenaire_id: int):
    partenaire = Partenaire.query.get_or_404(partenaire_id)

    if request.method == "POST":
        nom = (request.form.get("nom") or "").strip()
        if not nom:
            flash("Le nom du partenaire est obligatoire.", "danger")
            return redirect(url_for("partenaires.edit", partenaire_id=partenaire.id))

        partenaire.nom = nom
        partenaire.contact_nom = (request.form.get("contact_nom") or "").strip() or None
        partenaire.contact_prenom = (request.form.get("contact_prenom") or "").strip() or None
        partenaire.adresse = (request.form.get("adresse") or "").strip() or None
        partenaire.email_contact = (request.form.get("email_contact") or "").strip() or None
        partenaire.email_general = (request.form.get("email_general") or "").strip() or None
        partenaire.tel_contact = (request.form.get("tel_contact") or "").strip() or None
        partenaire.tel_general = (request.form.get("tel_general") or "").strip() or None
        partenaire.description = (request.form.get("description") or "").strip() or None

        secteurs = _selected_secteurs_from_request()
        PartenaireSecteur.query.filter_by(partenaire_id=partenaire.id).delete()
        for secteur in secteurs:
            db.session.add(PartenaireSecteur(partenaire_id=partenaire.id, secteur=secteur))

        db.session.commit()
        flash("Partenaire mis à jour.", "success")
        return redirect(url_for("partenaires.edit", partenaire_id=partenaire.id))

    secteurs = [s.secteur for s in partenaire.secteurs]
    return render_template("partenaires/form.html", partenaire=partenaire, secteurs=secteurs)


@bp.route("/<int:partenaire_id>/delete", methods=["POST"])
@login_required
@require_perm("partenaires:delete")
def delete(partenaire_id: int):
    partenaire = Partenaire.query.get_or_404(partenaire_id)
    db.session.delete(partenaire)
    db.session.commit()
    flash("Partenaire supprimé.", "success")
    return redirect(url_for("partenaires.index"))


@bp.route("/<int:partenaire_id>/interventions", methods=["POST"])
@login_required
@require_perm("partenaires:edit")
def add_intervention(partenaire_id: int):
    partenaire = Partenaire.query.get_or_404(partenaire_id)
    date_value = _parse_date(request.form.get("date_intervention"))
    if not date_value:
        flash("La date d'intervention est obligatoire.", "danger")
        return redirect(url_for("partenaires.edit", partenaire_id=partenaire.id))

    intervention = PartenaireIntervention(
        partenaire_id=partenaire.id,
        secteur=(request.form.get("secteur") or "").strip() or None,
        date_intervention=date_value,
        description=(request.form.get("description") or "").strip() or None,
        created_by_user_id=getattr(current_user, "id", None),
    )
    db.session.add(intervention)
    db.session.commit()
    flash("Intervention ajoutée.", "success")
    return redirect(url_for("partenaires.edit", partenaire_id=partenaire.id))


@bp.route("/<int:partenaire_id>/interventions/<int:intervention_id>/delete", methods=["POST"])
@login_required
@require_perm("partenaires:edit")
def delete_intervention(partenaire_id: int, intervention_id: int):
    partenaire = Partenaire.query.get_or_404(partenaire_id)
    intervention = PartenaireIntervention.query.filter_by(id=intervention_id, partenaire_id=partenaire.id).first()
    if not intervention:
        abort(404)
    db.session.delete(intervention)
    db.session.commit()
    flash("Intervention supprimée.", "success")
    return redirect(url_for("partenaires.edit", partenaire_id=partenaire.id))
