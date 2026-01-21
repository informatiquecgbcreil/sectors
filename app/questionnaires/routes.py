from __future__ import annotations

import csv
import json
from io import StringIO

from flask import render_template, request, redirect, url_for, flash, abort, Response
from flask_login import login_required, current_user

from app.extensions import db
from app.models import (
    Questionnaire,
    QuestionnaireSecteur,
    QuestionnaireAtelier,
    Question,
    QuestionnaireResponseGroup,
    QuestionResponse,
    AtelierActivite,
    SessionActivite,
    PresenceActivite,
    Participant,
)
from app.rbac import require_perm

from . import bp


QUESTION_TYPES = [
    ("scale", "Échelle 1-5"),
    ("yesno", "Oui / Non"),
    ("multi", "Choix multiple"),
    ("text", "Texte libre"),
]


def _selected_secteurs() -> list[str]:
    secteurs = request.values.getlist("secteur")
    cleaned = [s.strip() for s in secteurs if s and s.strip()]
    return list(dict.fromkeys(cleaned))


def _selected_ateliers() -> list[int]:
    ids = []
    for value in request.values.getlist("atelier_id"):
        try:
            ids.append(int(value))
        except Exception:
            continue
    return list(dict.fromkeys(ids))


def _questionnaires_for_session(session: SessionActivite) -> list[Questionnaire]:
    q = Questionnaire.query.filter_by(is_active=True).order_by(Questionnaire.nom.asc()).all()
    result = []
    for questionnaire in q:
        secteurs = {s.secteur for s in questionnaire.secteurs}
        ateliers = {a.atelier_id for a in questionnaire.ateliers}
        if secteurs and session.secteur not in secteurs:
            continue
        if ateliers and session.atelier_id not in ateliers:
            continue
        result.append(questionnaire)
    return result


@bp.route("/")
@login_required
@require_perm("questionnaires:view")
def index():
    q = (request.args.get("q") or "").strip()
    questionnaires = Questionnaire.query
    if q:
        like = f"%{q.lower()}%"
        questionnaires = questionnaires.filter(db.func.lower(Questionnaire.nom).like(like))
    questionnaires = questionnaires.order_by(Questionnaire.nom.asc()).all()
    ateliers = AtelierActivite.query.filter_by(is_deleted=False).all()
    ateliers_map = {a.id: f"{a.secteur} — {a.nom}" for a in ateliers}
    return render_template(
        "questionnaires/index.html",
        questionnaires=questionnaires,
        q=q,
        ateliers_map=ateliers_map,
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
@require_perm("questionnaires:edit")
def create():
    ateliers = AtelierActivite.query.filter_by(is_deleted=False).order_by(AtelierActivite.nom.asc()).all()
    if request.method == "POST":
        nom = (request.form.get("nom") or "").strip()
        if not nom:
            flash("Le nom du questionnaire est obligatoire.", "danger")
            return redirect(url_for("questionnaires.create"))

        questionnaire = Questionnaire(
            nom=nom,
            description=(request.form.get("description") or "").strip() or None,
            is_active=request.form.get("is_active") == "1",
        )
        db.session.add(questionnaire)
        db.session.flush()

        for secteur in _selected_secteurs():
            db.session.add(QuestionnaireSecteur(questionnaire_id=questionnaire.id, secteur=secteur))
        for atelier_id in _selected_ateliers():
            db.session.add(QuestionnaireAtelier(questionnaire_id=questionnaire.id, atelier_id=atelier_id))

        db.session.commit()
        flash("Questionnaire créé.", "success")
        return redirect(url_for("questionnaires.edit", questionnaire_id=questionnaire.id))

    return render_template(
        "questionnaires/form.html",
        questionnaire=None,
        secteurs=[],
        ateliers=ateliers,
        ateliers_selected=[],
        questions=[],
        question_types=QUESTION_TYPES,
    )


@bp.route("/<int:questionnaire_id>/edit", methods=["GET", "POST"])
@login_required
@require_perm("questionnaires:edit")
def edit(questionnaire_id: int):
    questionnaire = Questionnaire.query.get_or_404(questionnaire_id)
    ateliers = AtelierActivite.query.filter_by(is_deleted=False).order_by(AtelierActivite.nom.asc()).all()

    if request.method == "POST":
        nom = (request.form.get("nom") or "").strip()
        if not nom:
            flash("Le nom du questionnaire est obligatoire.", "danger")
            return redirect(url_for("questionnaires.edit", questionnaire_id=questionnaire.id))

        questionnaire.nom = nom
        questionnaire.description = (request.form.get("description") or "").strip() or None
        questionnaire.is_active = request.form.get("is_active") == "1"

        QuestionnaireSecteur.query.filter_by(questionnaire_id=questionnaire.id).delete()
        QuestionnaireAtelier.query.filter_by(questionnaire_id=questionnaire.id).delete()

        for secteur in _selected_secteurs():
            db.session.add(QuestionnaireSecteur(questionnaire_id=questionnaire.id, secteur=secteur))
        for atelier_id in _selected_ateliers():
            db.session.add(QuestionnaireAtelier(questionnaire_id=questionnaire.id, atelier_id=atelier_id))

        db.session.commit()
        flash("Questionnaire mis à jour.", "success")
        return redirect(url_for("questionnaires.edit", questionnaire_id=questionnaire.id))

    secteurs = [s.secteur for s in questionnaire.secteurs]
    ateliers_selected = [a.atelier_id for a in questionnaire.ateliers]
    questions = (
        Question.query.filter_by(questionnaire_id=questionnaire.id)
        .order_by(Question.position.asc(), Question.id.asc())
        .all()
    )
    return render_template(
        "questionnaires/form.html",
        questionnaire=questionnaire,
        secteurs=secteurs,
        ateliers=ateliers,
        ateliers_selected=ateliers_selected,
        questions=questions,
        question_types=QUESTION_TYPES,
    )


@bp.route("/<int:questionnaire_id>/delete", methods=["POST"])
@login_required
@require_perm("questionnaires:delete")
def delete(questionnaire_id: int):
    questionnaire = Questionnaire.query.get_or_404(questionnaire_id)
    db.session.delete(questionnaire)
    db.session.commit()
    flash("Questionnaire supprimé.", "success")
    return redirect(url_for("questionnaires.index"))


@bp.route("/<int:questionnaire_id>/questions/new", methods=["POST"])
@login_required
@require_perm("questionnaires:edit")
def add_question(questionnaire_id: int):
    questionnaire = Questionnaire.query.get_or_404(questionnaire_id)
    label = (request.form.get("label") or "").strip()
    if not label:
        flash("Le libellé de la question est obligatoire.", "danger")
        return redirect(url_for("questionnaires.edit", questionnaire_id=questionnaire.id))

    kind = (request.form.get("kind") or "text").strip()
    is_required = request.form.get("is_required") == "1"
    position = request.form.get("position")
    try:
        position_value = int(position) if position else 0
    except Exception:
        position_value = 0

    options_raw = (request.form.get("options") or "").strip()
    options_json = None
    if options_raw:
        options = [o.strip() for o in options_raw.split("\n") if o.strip()]
        options_json = json.dumps(options, ensure_ascii=False)

    db.session.add(
        Question(
            questionnaire_id=questionnaire.id,
            label=label,
            kind=kind,
            is_required=is_required,
            position=position_value,
            options_json=options_json,
        )
    )
    db.session.commit()
    flash("Question ajoutée.", "success")
    return redirect(url_for("questionnaires.edit", questionnaire_id=questionnaire.id))


@bp.route("/questions/<int:question_id>/delete", methods=["POST"])
@login_required
@require_perm("questionnaires:edit")
def delete_question(question_id: int):
    question = Question.query.get_or_404(question_id)
    questionnaire_id = question.questionnaire_id
    db.session.delete(question)
    db.session.commit()
    flash("Question supprimée.", "success")
    return redirect(url_for("questionnaires.edit", questionnaire_id=questionnaire_id))


@bp.route("/session/<int:session_id>", methods=["GET", "POST"])
@login_required
@require_perm("questionnaires:respond")
def respond(session_id: int):
    session = SessionActivite.query.get_or_404(session_id)
    atelier = AtelierActivite.query.get(session.atelier_id)
    questionnaires = _questionnaires_for_session(session)
    presences = (
        db.session.query(Participant)
        .join(PresenceActivite, PresenceActivite.participant_id == Participant.id)
        .filter(PresenceActivite.session_id == session.id)
        .order_by(Participant.nom.asc(), Participant.prenom.asc())
        .all()
    )

    selected_questionnaire_id = request.args.get("questionnaire_id")
    selected_participant_id = request.args.get("participant_id")
    selected_questionnaire = None
    if selected_questionnaire_id:
        try:
            selected_id = int(selected_questionnaire_id)
        except Exception:
            selected_id = None
        if selected_id:
            selected_questionnaire = next((q for q in questionnaires if q.id == selected_id), None)

    questions = []
    options_map: dict[int, list[str]] = {}
    if selected_questionnaire:
        questions = (
            Question.query.filter_by(questionnaire_id=selected_questionnaire.id)
            .order_by(Question.position.asc(), Question.id.asc())
            .all()
        )
        for question in questions:
            if question.options_json:
                try:
                    options_map[question.id] = json.loads(question.options_json)
                except Exception:
                    options_map[question.id] = []
            else:
                options_map[question.id] = []

    if request.method == "POST":
        questionnaire_id_raw = request.form.get("questionnaire_id")
        try:
            questionnaire_id = int(questionnaire_id_raw) if questionnaire_id_raw else None
        except Exception:
            questionnaire_id = None
        selected_questionnaire = next((q for q in questionnaires if q.id == questionnaire_id), None)
        if not selected_questionnaire:
            flash("Questionnaire invalide.", "danger")
            return redirect(url_for("questionnaires.respond", session_id=session.id))

        questions = (
            Question.query.filter_by(questionnaire_id=selected_questionnaire.id)
            .order_by(Question.position.asc(), Question.id.asc())
            .all()
        )
        participant_id_raw = request.form.get("participant_id")
        try:
            participant_id = int(participant_id_raw) if participant_id_raw else None
        except Exception:
            participant_id = None

        group = QuestionnaireResponseGroup(
            questionnaire_id=selected_questionnaire.id,
            participant_id=participant_id,
            session_id=session.id,
            atelier_id=session.atelier_id,
            secteur=session.secteur,
            created_by_user_id=getattr(current_user, "id", None),
        )
        db.session.add(group)
        db.session.flush()

        for question in questions:
            key = f"question_{question.id}"
            value = request.form.getlist(key) if question.kind == "multi" else request.form.get(key)
            response = QuestionResponse(response_group_id=group.id, question_id=question.id)
            if question.kind == "scale":
                try:
                    response.value_number = float(value) if value not in (None, "") else None
                except Exception:
                    response.value_number = None
            elif question.kind == "yesno":
                response.value_text = value or None
            elif question.kind == "multi":
                response.value_json = json.dumps(value or [], ensure_ascii=False)
            else:
                response.value_text = (value or "").strip() or None
            db.session.add(response)

        db.session.commit()
        flash("Réponses enregistrées.", "success")
        return redirect(
            url_for(
                "questionnaires.respond",
                session_id=session.id,
                questionnaire_id=selected_questionnaire.id,
                participant_id=participant_id or "",
            )
        )

    return render_template(
        "questionnaires/respond.html",
        session=session,
        atelier=atelier,
        questionnaires=questionnaires,
        selected_questionnaire=selected_questionnaire,
        questions=questions,
        presences=presences,
        options_map=options_map,
        selected_participant_id=selected_participant_id,
    )


@bp.route("/<int:questionnaire_id>/export.csv")
@login_required
@require_perm("questionnaires:export")
def export_csv(questionnaire_id: int):
    questionnaire = Questionnaire.query.get_or_404(questionnaire_id)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["questionnaire", "question", "participant_id", "session_id", "atelier_id", "secteur", "valeur", "date"])

    rows = (
        db.session.query(QuestionResponse, QuestionnaireResponseGroup, Question)
        .join(QuestionnaireResponseGroup, QuestionResponse.response_group_id == QuestionnaireResponseGroup.id)
        .join(Question, QuestionResponse.question_id == Question.id)
        .filter(QuestionnaireResponseGroup.questionnaire_id == questionnaire.id)
        .order_by(QuestionnaireResponseGroup.created_at.asc())
        .all()
    )

    for response, group, question in rows:
        if response.value_number is not None:
            value = response.value_number
        elif response.value_json:
            value = response.value_json
        else:
            value = response.value_text or ""
        writer.writerow(
            [
                questionnaire.nom,
                question.label,
                group.participant_id or "",
                group.session_id or "",
                group.atelier_id or "",
                group.secteur or "",
                value,
                group.created_at.strftime("%Y-%m-%d %H:%M") if group.created_at else "",
            ]
        )

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=questionnaire_{questionnaire.id}.csv"},
    )
