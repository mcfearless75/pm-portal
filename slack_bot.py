import os
import re
import requests
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.web import WebClient

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
API_BASE_URL   = os.getenv("API_BASE_URL","https://your-cv-portal.com")
API_KEY        = os.getenv("API_KEY")

app = App(token=SLACK_BOT_TOKEN)
client = WebClient(token=SLACK_BOT_TOKEN)

def parse_search_text(text: str):
    area, skills = None, []
    m_area = re.search(r'in\s+([\w\s]+?)\s+(?:with|$)', text, re.IGNORECASE)
    if m_area: area = m_area.group(1).strip()
    m_skills = re.search(r'with\s+([\w\s,]+)', text, re.IGNORECASE)
    if m_skills:
        skills = [s.strip().lower() for s in re.split(r'[ ,]+', m_skills.group(1)) if s.strip()]
    return area, skills

@app.command("/find_pms")
def handle_find_pms(ack, respond, command):
    ack()
    area, skills = parse_search_text(command.get("text",""))
    try:
        r = requests.post(f"{API_BASE_URL}/api/slack_search",
                          json={"area":area,"skills":skills},
                          headers={"Authorization":f"Bearer {API_KEY}"}, timeout=10)
        r.raise_for_status()
        results = r.json().get("results",[])
    except Exception as e:
        respond(f":warning: Error: {e}")
        return

    if not results:
        respond(f":mag: No candidates found in *{area or 'anywhere'}* with {', '.join(skills) or 'any skills'}.")
        return

    blocks = [{
        "type":"section",
        "text":{"type":"mrkdwn",
                "text":f"*Found {len(results)} candidates in {area or 'anywhere'} with {', '.join(skills)}*"}}
    ]
    for idx,item in enumerate(results[:5],1):
        u,item_cv = item["user"], item["resume"]
        blocks += [
            {"type":"section",
             "text":{"type":"mrkdwn",
                     "text":f"*{idx}. {u['name']}*\nArea: {u['area']} | Uploaded: {item_cv['upload_time']}\nSkills: {', '.join(item_cv['tags'])}"},
             "accessory":{"type":"button","text":{"type":"plain_text","text":"Download CV"},
                          "value":str(item_cv['id']),"action_id":"download_cv"}},
            {"type":"divider"}
        ]
    respond(blocks=blocks)

@app.action("download_cv")
def handle_download_cv(ack, body, client):
    ack()
    cv_id = body["actions"][0]["value"]
    user  = body["user"]["id"]
    r = requests.get(f"{API_BASE_URL}/api/cv/{cv_id}/download_link",
                     headers={"Authorization":f"Bearer {API_KEY}"}, timeout=10)
    if r.ok:
        link = r.json().get("download_url")
        client.chat_postEphemeral(channel=body["channel"]["id"], user=user,
                                   text=f":point_right: Download CV: {link}")
    else:
        client.chat_postEphemeral(channel=body["channel"]["id"], user=user,
                                   text=":warning: Unable to get download link.")

if __name__ == "__main__":
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
