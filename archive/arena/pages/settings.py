# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import mesop as me

from components.header import header
from components.page_scaffold import (
    page_scaffold,
    page_frame,
)

from typing import Any
from common import authz
from config.default import Default
from config.firebase_config import FirebaseClient

import asyncio
from google.cloud.firestore import AsyncClient, FieldFilter


cnfg = Default()
db = FirebaseClient(cnfg.IMAGE_FIREBASE_DB).get_client()

def settings_page_content(app_state: me.state):
    """Settings Mesop Page"""
    with page_scaffold():  # pylint: disable=not-context-manager
        with page_frame():  # pylint: disable=not-context-manager
            header("Settings", "settings")

            me.text(app_state.welcome_message, style=me.Style(font_style="italic"))

            me.box(style=me.Style(height=16))

            _render_study_info(_get_studies(), app_state)

            me.box(style=me.Style(height=16))

            me.text(f"Vote pause time: {Default.SHOW_RESULTS_PAUSE_TIME} seconds")


async def _purge_elo_ratings(study: str, caller_email: str | None = None) -> bool:
    """Reset the ELO Ratings.

    Fail-closed authorization gate: refuse the destructive purge unless
    ``caller_email`` is a verified, allowlisted admin. The check runs *before*
    any Firestore client is constructed or any document is read/deleted, so an
    unauthorized/unauthenticated caller deletes nothing and gets no existence
    oracle. See ``common/authz.py`` (mirrors main-app PRs #1920 / #1930).
    """
    authz.authorize_admin(caller_email, action="reset the leaderboard")

    db = AsyncClient(project=cnfg.PROJECT_ID, database=cnfg.IMAGE_FIREBASE_DB)

    batch_transcations = db.batch()
    ratings = db.collection("arena_elo")
    docs = ratings.where(filter=FieldFilter("study", "==", study)).stream()

    batches = []
    idx = 0
    async for doc in docs:
        doc_ref = doc.reference
        batch_transcations.delete(doc_ref)

        if((idx + 1) % 1000 == 0):
            batches.append(batch_transcations.commit(timeout=60))
            batch_transcations = db.batch()
        idx += 1
        idx = idx % 1000
    
    if batch_transcations:
        batches.append(batch_transcations.commit(timeout=60))
    
    results = await asyncio.gather(*batches)

    return all(results)

def _get_studies() -> dict[dict[str, Any]]:
    """ Get all Studies """
    studies = dict()
    docs = db.collection(cnfg.STUDY_COLLECTION_NAME).stream()
    for doc in docs:
        doc_content = doc.to_dict()
        studies.update({doc_content['label']: doc_content})
    studies.update({"live": {"label": "live", "gcsuri": "imagen_prompts.json"}})
    return studies

def _render_study_info(studies: dict[dict[str, Any]], app_state: me.state):
    """Render the Mesop Studies"""
    def _handle_select(study: me.ClickEvent):
        app_state.study = study.key
        app_state.study_prompts_location = studies[study.key]['gcsuri']
        app_state.study_models = studies[study.key].get('models', [])
    
    def _handle_purge(study: me.ClickEvent):
        # Resolve the server-*verified* caller and authorize before doing
        # anything destructive. Arena has no verified-identity pipeline yet, so
        # this currently resolves to None and the purge fails closed (no data is
        # touched) until a verified identity is wired. See common/authz.py.
        caller_email = authz.get_verified_caller_email()
        try:
            authz.authorize_admin(caller_email, action="reset the leaderboard")
        except authz.AuthorizationError as exc:
            print(f"Reset Leaderboard denied: {exc}")
            return
        asyncio.run(_purge_elo_ratings(study=study.key, caller_email=caller_email))
    
    if len(studies):
        me.text("Available Studies", type="headline-5")

        for study in studies.keys():
            
            with me.box(style=_BOX_STYLE):
                this_study = studies[study]

                study_modifier = "Available"
                if app_state.study == study:
                    study_modifier = "Current"
                me.text(f"{study_modifier} Study: {this_study['label']}", style=me.Style(font_weight="bold"))
                me.box(style=me.Style(height=8))

                models = this_study.get("models")
                model_list_items = ""
                if models:
                    for model in models:
                        model_list_items += f"<li>{model}</li>"
                else:
                    model_list_items = """
                    <li>imagen-4.0-generate-001</li>
                    <li>imagen-4.0-fast-generate-001</li>
                    <li>black-forest-labs/flux1-schnell</li>
                    <li>stability-ai/stable-diffusion-2-1</li>
                    """
                me.html(f"Models <ul>{model_list_items}</ul>")


                me.text(f"Prompt list: {this_study['gcsuri']}")
                #for key, value in studies[study].items():
                #    me.markdown(f"**{key}:** {value}")


                if app_state.study != study:
                    me.button(
                        label="Activate", 
                        on_click=lambda study=study: _handle_select(study), 
                        key=study, 
                        disabled=app_state.study == study,
                    )
                

            me.box(style=me.Style(height=16))
                
            #me.divider(inset=False)

        me.box(style=me.Style(height=16))

        me.button(label="Reset Leaderboard for current study", 
           on_click=lambda study=app_state.study: _handle_purge(study), key=f"{app_state.study}")
            
    else:
        me.markdown("No Studies found")

_BOX_STYLE = me.Style(
    flex_basis="max(480px, calc(50% - 48px))",
    background=me.theme_var("background"),
    border_radius=12,
    box_shadow=("0 3px 1px -2px #0003, 0 2px 2px #00000024, 0 1px 5px #0000001f"),
    padding=me.Padding(top=16, left=16, right=16, bottom=16),
    display="flex",
    flex_direction="column",
    #width="100%",
)