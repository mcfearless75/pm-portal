slack_bot.pyimport os
import re
import requests
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.web import WebClient

# --- CONFIG ---
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")           # xoxb-...
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")           # xapp-...
API_BASE_URL     = os.getenv("API_BASE_URL", "https://your-cv-portal.com")
API_KEY          = os.getenv("API_KEY")                  # Secure token to authenticate with your Flask backend

# Initialize Bolt app
app = App(token=SLACK_BOT_TOKEN)
client = WebClient(token=SLACK_BOT_TOKEN)

# Utility: parse command text for area & skills
def parse_search_text(text: str):
    # crude parsing: look for 'in <area>' and skills after 'with'
    area = None
    skills = []
    m_area = re.search(r'in\s+([\w\s]+?)\s+(?:with|$)', text, re.IGNORECASE)
    if m_area:
        area = m_area.group(1).strip()
    m_skills = re.search(r'with\s+([\w\s,]+)', text, re.IGNORECASE)
    if m_skills:
        skills = [s.strip().lower() for s in re.split(r'[ ,]+', m_skills.group(1)) if s.strip()]
    return area, skills

# Slash command: /find_pms
@app.command("/find_pms")
def handle_find_pms(ack, respond, command):
    ack()
    user_text = command.get("text", "")
    area, skills = parse_search_text(user_text)

    # Call backend search API
    try:
        headers = {"Authorization": f"Bearer {API_KEY}"}
        payload = {"area": area, "skills": skills}
        r = requests.post(f"{API_BASE_URL}/api/slack_search", json=payload, headers=headers, timeout=10)
        r.raise_for_status()
        results = r.json().get("results", [])
    except Exception as e:
        respond(f":warning: Error querying candidate database: {e}")
        return

    if not results:
        respond(f":mag: No PMs found in *{area or 'anywhere'}* with {', '.join(skills) or 'no specific skills'}.")
        return

    # Build blocks for summary card
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Found {len(results)} PM candidates in {area or 'anywhere'} with skills: {', '.join(skills)}*"}}
    ]
    for idx, item in enumerate(results[:5], 1):  # Top 5
        user = item.get("user")
        cv = item.get("resume")
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{idx}. {user['name']}*\nArea: {user.get('area')} | Uploaded: {cv.get('upload_time')}\nSkills: {', '.join(cv.get('tags', []))}"},
            "accessory": {"type": "button", "text": {"type": "plain_text", "text": "Download CV"}, "value": str(cv['id']), "action_id": "download_cv"}
        })
        blocks.append({"type": "divider"})

    respond(blocks=blocks)

# Action: download CV button
@app.action("download_cv")
def handle_download_cv(ack, body, client):
    ack()
    cv_id = body["actions"][0]["value"]
    user_id = body["user"]["id"]
    # Generate presigned download link from backend
    headers = {"Authorization": f"Bearer {API_KEY}"}
    r = requests.get(f"{API_BASE_URL}/api/cv/{cv_id}/download_link", headers=headers, timeout=10)
    if r.status_code == 200:
        link = r.json().get("download_url")
        client.chat_postEphemeral(channel=body["channel"]["id"], user=user_id,
                                   text=f":point_right: Download CV: {link}")
    else:
        client.chat_postEphemeral(channel=body["channel"]["id"], user=user_id,
                                   text=":warning: Unable to get download link.")

if __name__ == "__main__":
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
