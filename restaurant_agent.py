from flask import Flask, request, Response, jsonify
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI
import json
from datetime import datetime
import os
from dotenv import load_dotenv
from restaurant_config import RESTAURANT_NAME

# Charger les variables d'environnement
load_dotenv()

app = Flask(__name__)


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MEMORY_TIMEOUT = int(os.getenv("MEMORY_TIMEOUT", "1800"))

# Initialiser OpenAI
try:
    client = OpenAI(api_key=OPENAI_API_KEY)
    print("✅ Client OpenAI initialisé")
except Exception as e:
    print(f"❌ Erreur OpenAI: {e}")
    client = None

# Stockage avec timestamps
conversations = {}  # {call_sid: [{"role":.., "content":.., "time":..}]}


# ==================== IA MÉMOIRE RENFORCÉE ====================
def get_ai_response(history, user_input):
    """IA avec MÉMOIRE INTELLIGENTE"""

    # RÉSUMÉ COMMANDE COURANTE
    resume = "Nouvelle commande"
    if len(history) >= 2:
        last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
        if last_user:
            resume = f"Commande: {last_user}"

    # ÉTAT conversation (détecte automatiquement)
    etape = "articles" if len(history) < 4 else "livraison" if len(history) < 8 else "infos_client"

    system_message = f"""🍕 {RESTAURANT_NAME} - Assistant MÉMOIRE.

📋 COMMANDE EN COURS: {resume}
📍 ÉTAPE: {etape}

🎯 1 QUESTION PRÉCISE:
1. Articles/quantités/sauces
2. Livraison/emporter?
3. Nom + téléphone
4. Adresse (si livraison)
5. Paiement
6. RÉCAP + total
7. END_CALL au au revoir

✅ STRICT:
• MAX 12 MOTS
• JAMAIS oublier commande
• Question SUIVANTE seulement
• Ton chaleureux"""

    messages = [{"role": "system", "content": system_message}]
    messages.extend(history[-10:])  # 10 messages mémoire
    messages.append({"role": "user", "content": user_input})

    try:
        if client is None:
            return "Service temporairement indisponible."

        response = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",
            messages=messages,
            temperature=0.1,
            max_tokens=60,
            timeout=2
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"❌ IA Error: {e}")
        return "Livraison ou emporter pour votre commande?"


# Nettoyage mémoire automatique
def cleanup_old_conversations():
    now = datetime.now()
    to_delete = []
    for call_sid, conv in conversations.items():
        if conv and len(conv) > 20:  # Conversation trop longue
            to_delete.append(call_sid)
        elif conv and (now - conv[-1]["time"]).seconds > MEMORY_TIMEOUT:
            to_delete.append(call_sid)
    for sid in to_delete:
        del conversations[sid]


# ==================== ROUTES VOCALES ====================
@app.route("/voice", methods=["POST"])
def voice():
    response = VoiceResponse()
    response.say(
        f'Bonjour chez {RESTAURANT_NAME}! Votre commande?',
        language="fr-FR", voice="Google.fr-FR-Neural2-B"
    )

    gather = Gather(input="speech", language="fr-FR", speechTimeout="2",
                    action="/process", method="POST", bargeIn=True,
                    timeout=12, hints="pizza burger kebab tacos frites oui non")
    response.append(gather)
    return Response(str(response), mimetype="text/xml")


@app.route("/process", methods=["POST"])
def process():
    speech = request.values.get("SpeechResult", "").strip()
    call_sid = request.values.get("CallSid", "")[:8]

    print(f"📞 [{call_sid}] 👤 {speech}")

    # Initialiser avec timestamp
    if call_sid not in conversations:
        conversations[call_sid] = []

    conv = conversations[call_sid]

    # Ajouter timestamp
    conv.append({
        "role": "user",
        "content": speech,
        "time": datetime.now()
    })

    ai_reply = get_ai_response(conv[:-1], speech)  # Passe sans dernier user
    print(f"📞 [{call_sid}] 🤖 {ai_reply}")

    conv.append({
        "role": "assistant",
        "content": ai_reply,
        "time": datetime.now()
    })

    # Fin d'appel intelligente
    if any(word in ai_reply.upper() for word in ["END_CALL", "MERCI", "AU REVOIR", "C'EST BON"]):
        response = VoiceResponse()
        response.say("Commande prise! Bonne journée!",
                     language="fr-FR", voice="Google.fr-FR-Neural2-B")
        print(f"📴 [{call_sid}] ✅ TERMINÉ")
        return Response(str(response), mimetype="text/xml")

    # Continue conversation
    response = VoiceResponse()
    response.say(ai_reply, language="fr-FR", voice="Google.fr-FR-Neural2-B")

    gather = Gather(input="speech", language="fr-FR", speechTimeout="2",
                    action="/process", method="POST", timeout=12, bargeIn=True)
    response.append(gather)

    cleanup_old_conversations()
    return Response(str(response), mimetype="text/xml")


# ==================== APIs ====================
@app.route("/")
def home():
    cleanup_old_conversations()
    return jsonify({
        "status": "🟢 ACTIF",
        "restaurant": RESTAURANT_NAME,
        "actives": len(conversations),
        "universal": True
    })


@app.route("/api/stats")
def stats():
    cleanup_old_conversations()
    return jsonify({
        "conversations": len(conversations),
        "restaurant": RESTAURANT_NAME
    })


@app.route("/clear", methods=["POST"])
def clear():
    global conversations
    conversations.clear()
    return jsonify({"cleared": True})


# Nettoyage après chaque requête
@app.after_request
def after_request(response):
    cleanup_old_conversations()
    return response


# ==================== LAUNCH ====================
if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("🧠 AGENT IA RESTO - MÉMOIRE FIXÉE")
    print("=" * 50)
    print(f"🏪 {RESTAURANT_NAME}")
    print("✅ Mémoire renforcée")
    print("✅ Nettoyage auto 30min")
    print("✅ <1.5s latence")
    print("\n🚀 http://localhost:5000/voice")
    print("=" * 50)

    app.run(debug=False, port=5000, host="0.0.0.0")
