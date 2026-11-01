# -*- coding: utf-8 -*-
"""Point d'entrée de l'app CGF Gestion — marché obligataire UMOA.

Lancement :  streamlit run app/Accueil.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.lib import chargement, courbes  # noqa: E402

st.set_page_config(page_title="Marché obligataire UMOA — CGF Gestion",
                   page_icon="📈", layout="wide")

st.title("Marché obligataire UMOA")
st.caption("Référentiel des titres, marché primaire et secondaire, courbes de "
           "taux et risque de taux — sources UMOA-Titres et BRVM.")

reference = chargement.date_reference()
st.markdown(f"**Date de référence des calculs : {reference:%d/%m/%Y}** — "
            "la plus récente observation disponible, jamais l'horloge système, "
            "pour que maturités et prix restent cohérents entre eux.")

st.subheader("Fraîcheur des sources")
etat = chargement.fraicheur().copy()
etat["Dernière donnée"] = etat["Dernière donnée"].dt.strftime("%d/%m/%Y")
st.dataframe(etat, hide_index=True, width="stretch")

perimees = courbes.fraicheur_courbes()
en_retard = perimees[perimees["Périmée"]]
if not en_retard.empty:
    st.warning(
        f"{len(en_retard)} courbe(s) pays datent de plus de "
        f"{courbes.ParametresCourbe().seuil_fraicheur_jours} jours : "
        + ", ".join(en_retard["Pays"]) + ". Les taux de référence affichés "
        "ailleurs dans l'app sont ceux de la dernière publication connue.")

st.subheader("Pages")
st.markdown("""
- **Référentiel** — l'univers complet des titres, la répartition coté / non coté
  et la liste exhaustive filtrable.
- **Fiche titre** — tout ce que les trois sources savent d'une souche : son
  émission, sa vie secondaire et sa cotation. Accessible par drill depuis le
  référentiel, ou directement par `?titre=<ISIN>` dans l'URL.
- **Courbes** — les trois niveaux de lecture (brut, officielle UMOA-Titres,
  reconstruction CGF), les réglages de cette reconstruction et le diagnostic
  de qualité des courbes publiées.
- **Marché primaire** — adjudications, taux de couverture, coût de financement
  effectivement servi et tension des enchères.
- **Marché secondaire** — activité, liquidité, qualité d'exécution et prints
  atypiques.
- **Benchmark** — indice composite 30 / 70, contributions et limites
  méthodologiques.
- **Risque de taux** — duration, convexité, DV01 et scénarios de déformation
  de courbe, pondérés par l'encours.
- **Calendrier des émissions** — la seule source prospective : agenda des
  séances à venir (exportable en `.ics`), cadence de venue au marché des huit
  Trésors et rapprochement de chaque annonce avec son résultat d'adjudication.
- **Simulateur** — valorisation complète d'une souche (échéancier daté, prix,
  duration, convexité) au service de deux décisions : à quel taux
  soumissionner à une adjudication, et à partir de quel taux de replacement
  vendre une ligne détenue devient préférable à la conserver.

Reste à venir : une page Qualité des données rassemblant les diagnostics de
fraîcheur, d'appariement et d'anomalies de source.
""")

reglages = st.session_state.get(courbes.CLE_ETAT)
if reglages:
    st.info("Des réglages de courbe CGF personnalisés sont actifs pour cette "
            "session : ils s'appliquent au référentiel et aux fiches titre. "
            "La page Courbes permet de les revoir.")
